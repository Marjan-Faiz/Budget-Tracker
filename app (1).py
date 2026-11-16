import sqlite3
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

DB = "budget.db"
CUR = "Rs"
EXPENSE_CATS = ["Khana", "Transport", "Bills", "Kiraya", "Shopping", "Sehat", "Taleem", "Entertainment", "Other"]
INCOME_CATS = ["Salary", "Business", "Gift", "Other"]

st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="centered")


def conn():
    return sqlite3.connect(DB)


def init_db():
    with conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS transactions("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, type TEXT, "
            "category TEXT, amount REAL, note TEXT)"
        )
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
        c.execute(
            "CREATE TABLE IF NOT EXISTS savings_goals("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, target REAL)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS savings_tx("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER, date TEXT, "
            "amount REAL, note TEXT)"
        )


def load_tx():
    with conn() as c:
        df = pd.read_sql("SELECT * FROM transactions ORDER BY date DESC, id DESC", c)
    df["date"] = pd.to_datetime(df["date"])
    return df


def add_tx(d, t, cat, amt, note):
    with conn() as c:
        c.execute(
            "INSERT INTO transactions(date,type,category,amount,note) VALUES(?,?,?,?,?)",
            (d.isoformat(), t, cat, amt, note),
        )


def delete_tx(tx_id):
    with conn() as c:
        c.execute("DELETE FROM transactions WHERE id=?", (tx_id,))


def get_setting(key, default=0.0):
    with conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return float(row[0]) if row else default


def set_setting(key, value):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))


def load_goals():
    with conn() as c:
        return pd.read_sql(
            "SELECT g.id, g.name, g.target, COALESCE(SUM(t.amount),0) AS saved "
            "FROM savings_goals g LEFT JOIN savings_tx t ON t.goal_id=g.id "
            "GROUP BY g.id ORDER BY g.id",
            c,
        )


def load_savings_tx():
    with conn() as c:
        return pd.read_sql(
            "SELECT t.id, t.date, g.name AS goal, t.amount, t.note "
            "FROM savings_tx t JOIN savings_goals g ON g.id=t.goal_id "
            "ORDER BY t.date DESC, t.id DESC",
            c,
        )


def money(x):
    return f"{CUR} {x:,.0f}"


init_db()
st.title("💰 Budget Tracker")
tab_dash, tab_add, tab_hist, tab_save, tab_budget, tab_backup = st.tabs(
    ["📊 Dashboard", "➕ Add", "📜 History", "🏦 Savings", "🎯 Budget", "💾 Backup"]
)

df = load_tx()
today = pd.Timestamp(date.today())
month_df = df[(df["date"].dt.year == today.year) & (df["date"].dt.month == today.month)]
exp_m = month_df[month_df["type"] == "Expense"]
inc_m = month_df[month_df["type"] == "Income"]

# ---------------- Dashboard ----------------
with tab_dash:
    today_spent = df[(df["date"] == today) & (df["type"] == "Expense")]["amount"].sum()
    week_start = today - pd.Timedelta(days=today.weekday())
    week_spent = df[(df["date"] >= week_start) & (df["type"] == "Expense")]["amount"].sum()
    month_spent = exp_m["amount"].sum()
    month_income = inc_m["amount"].sum()
    savings = month_income - month_spent

    c1, c2, c3 = st.columns(3)
    c1.metric("Aaj ka kharcha", money(today_spent))
    c2.metric("Is hafte", money(week_spent))
    c3.metric("Is mahine", money(month_spent))
    c4, c5, c6 = st.columns(3)
    c4.metric("Income (is mahine)", money(month_income))
    c5.metric("Bachat (income - kharcha)", money(savings))
    c6.metric("Total savings jama", money(load_goals()["saved"].sum()))

    budget = get_setting("monthly_budget")
    if budget > 0:
        used = month_spent / budget
        st.write(f"**Monthly budget:** {money(month_spent)} / {money(budget)} ({used:.0%})")
        st.progress(min(used, 1.0))
        if used >= 1:
            st.error("Budget khatam ho chuka hai!")
        elif used >= 0.8:
            st.warning("Budget ka 80% se zyada kharch ho gaya.")
        else:
            st.success(f"Abhi {money(budget - month_spent)} bacha hai.")
    else:
        st.info("Budget tab mein monthly budget set karein.")

    goal = get_setting("savings_goal")
    if goal > 0:
        st.write(f"**Savings goal:** {money(max(savings, 0))} / {money(goal)}")
        st.progress(min(max(savings, 0) / goal, 1.0))

    st.subheader("Category ke hisab se kharcha")
    if exp_m.empty:
        st.caption("Is mahine abhi koi kharcha nahi.")
    else:
        by_cat = exp_m.groupby("category", as_index=False)["amount"].sum()
        st.plotly_chart(px.pie(by_cat, names="category", values="amount", hole=0.4), use_container_width=True)
        for _, r in by_cat.iterrows():
            lim = get_setting(f"limit:{r['category']}")
            if lim > 0 and r["amount"] >= lim:
                st.warning(f"{r['category']}: limit {money(lim)} cross ho gayi ({money(r['amount'])})")

        st.subheader("Rozana kharcha")
        daily = exp_m.groupby("date", as_index=False)["amount"].sum()
        st.plotly_chart(px.bar(daily, x="date", y="amount"), use_container_width=True)

# ---------------- Add ----------------
with tab_add:
    t = st.radio("Type", ["Expense", "Income"], horizontal=True)
    with st.form("add_form", clear_on_submit=True):
        d = st.date_input("Date", value=date.today())
        amt = st.number_input(f"Amount ({CUR})", min_value=0.0, step=50.0)
        cat = st.selectbox("Category", EXPENSE_CATS if t == "Expense" else INCOME_CATS)
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Save"):
            if amt <= 0:
                st.error("Amount 0 se zyada hona chahiye.")
            else:
                add_tx(d, t, cat, amt, note)
                st.success("Save ho gaya ✅")
                st.rerun()

# ---------------- History ----------------
with tab_hist:
    if df.empty:
        st.caption("Abhi koi entry nahi.")
    else:
        f1, f2 = st.columns(2)
        start = f1.date_input("From", value=df["date"].min().date(), key="h_from")
        end = f2.date_input("To", value=date.today(), key="h_to")
        view = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)]
        st.dataframe(
            view.assign(date=view["date"].dt.date),
            use_container_width=True,
            hide_index=True,
        )
        st.write(
            f"Kharcha: **{money(view[view['type']=='Expense']['amount'].sum())}** | "
            f"Income: **{money(view[view['type']=='Income']['amount'].sum())}**"
        )
        with st.expander("Entry delete karein"):
            del_id = st.number_input("Entry ID", min_value=1, step=1)
            if st.button("Delete"):
                delete_tx(int(del_id))
                st.rerun()

# ---------------- Savings ----------------
with tab_save:
    goals = load_goals()
    st.metric("Total savings jama", money(goals["saved"].sum()))

    with st.expander("➕ Naya savings goal", expanded=goals.empty):
        with st.form("goal_form", clear_on_submit=True):
            g_name = st.text_input("Goal ka naam (e.g. Emergency Fund, Bike)")
            g_target = st.number_input(f"Target ({CUR})", min_value=0.0, step=5000.0)
            if st.form_submit_button("Goal banayen"):
                if not g_name.strip() or g_target <= 0:
                    st.error("Naam aur target dono zaroori hain.")
                else:
                    try:
                        with conn() as c:
                            c.execute(
                                "INSERT INTO savings_goals(name,target) VALUES(?,?)",
                                (g_name.strip(), g_target),
                            )
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Is naam ka goal pehle se hai.")

    if goals.empty:
        st.info("Pehle ek savings goal banayen.")
    else:
        for _, g in goals.iterrows():
            pct = g["saved"] / g["target"] if g["target"] else 0
            st.write(f"**{g['name']}**: {money(g['saved'])} / {money(g['target'])} ({pct:.0%})")
            st.progress(min(max(pct, 0.0), 1.0))
            if pct >= 1:
                st.success("Goal mukammal! 🎉")

        st.subheader("Paise jama ya nikalen")
        with st.form("sav_form", clear_on_submit=True):
            pick = st.selectbox("Goal", goals["name"].tolist())
            action = st.radio("Action", ["Jama (Deposit)", "Nikalna (Withdraw)"], horizontal=True)
            s_date = st.date_input("Date", value=date.today(), key="s_date")
            s_amt = st.number_input(f"Amount ({CUR})", min_value=0.0, step=500.0, key="s_amt")
            s_note = st.text_input("Note (optional)", key="s_note")
            if st.form_submit_button("Save"):
                row = goals[goals["name"] == pick].iloc[0]
                if s_amt <= 0:
                    st.error("Amount 0 se zyada hona chahiye.")
                elif action.startswith("Nikalna") and s_amt > row["saved"]:
                    st.error(f"Itne paise jama nahi hain (maujooda: {money(row['saved'])}).")
                else:
                    signed = s_amt if action.startswith("Jama") else -s_amt
                    with conn() as c:
                        c.execute(
                            "INSERT INTO savings_tx(goal_id,date,amount,note) VALUES(?,?,?,?)",
                            (int(row["id"]), s_date.isoformat(), signed, s_note),
                        )
                    st.rerun()

        st.subheader("Savings history")
        stx = load_savings_tx()
        if stx.empty:
            st.caption("Abhi koi entry nahi.")
        else:
            st.dataframe(stx, use_container_width=True, hide_index=True)
            with st.expander("Entry ya goal delete karein"):
                d_id = st.number_input("Savings entry ID", min_value=1, step=1)
                if st.button("Entry delete"):
                    with conn() as c:
                        c.execute("DELETE FROM savings_tx WHERE id=?", (int(d_id),))
                    st.rerun()
                d_goal = st.selectbox("Goal", goals["name"].tolist(), key="del_goal")
                if st.button("Goal delete (uski entries bhi)"):
                    gid = int(goals[goals["name"] == d_goal].iloc[0]["id"])
                    with conn() as c:
                        c.execute("DELETE FROM savings_tx WHERE goal_id=?", (gid,))
                        c.execute("DELETE FROM savings_goals WHERE id=?", (gid,))
                    st.rerun()

# ---------------- Budget ----------------
with tab_budget:
    mb = st.number_input("Monthly budget", min_value=0.0, step=1000.0, value=get_setting("monthly_budget"))
    sg = st.number_input("Savings goal (monthly)", min_value=0.0, step=1000.0, value=get_setting("savings_goal"))
    st.write("**Category limits** (0 = koi limit nahi)")
    limits = {c: st.number_input(c, min_value=0.0, step=500.0, value=get_setting(f"limit:{c}"), key=f"lim_{c}")
              for c in EXPENSE_CATS}
    if st.button("Budget save karein"):
        set_setting("monthly_budget", mb)
        set_setting("savings_goal", sg)
        for c, v in limits.items():
            set_setting(f"limit:{c}", v)
        st.success("Save ho gaya ✅")

# ---------------- Backup ----------------
with tab_backup:
    st.caption("Streamlit Cloud par data restart par ud sakta hai, is liye regular backup download karein.")
    st.download_button("⬇️ Backup (CSV)", df.to_csv(index=False).encode(), "budget_backup.csv", "text/csv")
    st.download_button("⬇️ Savings backup (CSV)", load_savings_tx().to_csv(index=False).encode(),
                       "savings_backup.csv", "text/csv")
    up = st.file_uploader("Backup restore karein", type="csv")
    if up is not None and st.button("Restore"):
        new = pd.read_csv(up)
        need = {"date", "type", "category", "amount", "note"}
        if not need.issubset(new.columns):
            st.error("CSV ke columns galat hain.")
        else:
            with conn() as c:
                c.execute("DELETE FROM transactions")
                new[["date", "type", "category", "amount", "note"]].assign(
                    date=pd.to_datetime(new["date"]).dt.date.astype(str)
                ).to_sql("transactions", c, if_exists="append", index=False)
            st.success("Restore ho gaya ✅")
            st.rerun()
