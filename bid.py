import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime
from fpdf import FPDF
import base64

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Handyman Bid Pro", layout="wide", page_icon="🛠️")

# --- DATABASE SETUP (SQLite) ---
def init_db():
    conn = sqlite3.connect('handyman_jobs.db')
    c = conn.cursor()
    # Create Customers Table
    c.execute('''CREATE TABLE IF NOT EXISTS customers
                 (id INTEGER PRIMARY KEY, name TEXT, email TEXT, phone TEXT, address TEXT)''')
    # Create Bids Table
    c.execute('''CREATE TABLE IF NOT EXISTS bids
                 (id INTEGER PRIMARY KEY, customer_id INTEGER, project_name TEXT, 
                  date_created TEXT, items_json TEXT, subtotal REAL, 
                  markup_pct REAL, tax_pct REAL, total REAL, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTIONS ---
def get_connection():
    return sqlite3.connect('handyman_jobs.db')

def add_customer(name, email, phone, address):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO customers (name, email, phone, address) VALUES (?, ?, ?, ?)", 
              (name, email, phone, address))
    conn.commit()
    conn.close()

def get_customers():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM customers", conn)
    conn.close()
    return df

def save_bid(customer_id, project_name, items_df, subtotal, markup, tax, total):
    conn = get_connection()
    c = conn.cursor()
    items_json = items_df.to_json(orient='records')
    date_created = datetime.now().strftime("%Y-%m-%d")
    c.execute('''INSERT INTO bids (customer_id, project_name, date_created, items_json, 
                 subtotal, markup_pct, tax_pct, total, status) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (customer_id, project_name, date_created, items_json, subtotal, markup, tax, total, "Draft"))
    conn.commit()
    conn.close()
    return c.lastrowid

def get_bids():
    conn = get_connection()
    query = '''
    SELECT bids.id, bids.date_created, customers.name as customer, bids.project_name, bids.total, bids.status, bids.items_json
    FROM bids
    JOIN customers ON bids.customer_id = customers.id
    ORDER BY bids.id DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def update_bid_status(bid_id, new_status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE bids SET status = ? WHERE id = ?", (new_status, bid_id))
    conn.commit()
    conn.close()

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Job Estimate / Quote', 0, 1, 'C')
        self.ln(10)

def create_pdf(customer_name, project_name, items_df, totals):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Info
    pdf.cell(200, 10, txt=f"Customer: {customer_name}", ln=1)
    pdf.cell(200, 10, txt=f"Project: {project_name}", ln=1)
    pdf.cell(200, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=1)
    pdf.ln(10)
    
    # Table Header
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(80, 10, "Description", 1, 0, 'L', 1)
    pdf.cell(30, 10, "Mat. Cost", 1, 0, 'R', 1)
    pdf.cell(30, 10, "Labor Hrs", 1, 0, 'R', 1)
    pdf.cell(40, 10, "Total", 1, 1, 'R', 1)
    
    # Table Body
    for index, row in items_df.iterrows():
        line_total = row['Material Cost'] + (row['Labor Hours'] * row['Hourly Rate'])
        pdf.cell(80, 10, str(row['Description']), 1)
        pdf.cell(30, 10, f"${row['Material Cost']:.2f}", 1, 0, 'R')
        pdf.cell(30, 10, str(row['Labor Hours']), 1, 0, 'R')
        pdf.cell(40, 10, f"${line_total:.2f}", 1, 1, 'R')
        
    pdf.ln(10)
    
    # Totals
    pdf.cell(140, 10, "Subtotal:", 0, 0, 'R')
    pdf.cell(40, 10, f"${totals['subtotal']:.2f}", 0, 1, 'R')
    
    pdf.cell(140, 10, f"Markup ({totals['markup']}%):", 0, 0, 'R')
    pdf.cell(40, 10, f"${totals['markup_amt']:.2f}", 0, 1, 'R')
    
    pdf.cell(140, 10, f"Tax ({totals['tax']}%):", 0, 0, 'R')
    pdf.cell(40, 10, f"${totals['tax_amt']:.2f}", 0, 1, 'R')
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(140, 10, "TOTAL QUOTE:", 0, 0, 'R')
    pdf.cell(40, 10, f"${totals['total']:.2f}", 0, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# --- UI LAYOUT ---

st.title("🛠️ Handyman Bid Calculator & Manager")

# Sidebar Navigation
menu = st.sidebar.radio("Menu", ["New Estimate", "Client Database", "Bid History"])

# --- TAB: CLIENT DATABASE ---
if menu == "Client Database":
    st.header("Manage Clients")
    
    with st.expander("Add New Client", expanded=False):
        with st.form("new_client_form"):
            c_name = st.text_input("Client Name")
            c_email = st.text_input("Email")
            c_phone = st.text_input("Phone")
            c_address = st.text_area("Address")
            submitted = st.form_submit_button("Save Client")
            if submitted:
                if c_name:
                    add_customer(c_name, c_email, c_phone, c_address)
                    st.success(f"Client {c_name} added!")
                    st.rerun()
                else:
                    st.error("Name is required.")

    st.subheader("Existing Clients")
    clients = get_customers()
    # UPDATED: Replaced use_container_width=True with width="stretch"
    st.dataframe(clients, width="stretch")

# --- TAB: NEW ESTIMATE ---
elif menu == "New Estimate":
    st.header("Create New Job Bid")
    
    clients = get_customers()
    
    if clients.empty:
        st.warning("Please add a client in the 'Client Database' tab first.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            client_list = clients.set_index('id')['name'].to_dict()
            selected_client_id = st.selectbox("Select Client", options=list(client_list.keys()), format_func=lambda x: client_list[x])
        with col2:
            project_name = st.text_input("Project Name (e.g., Kitchen Painting)")

        st.subheader("Job Details (Line Items)")
        st.info("💡 Tip: Enter materials and labor for each task. Leave Hourly Rate as 0 for material-only items.")

        # Data Editor for Line Items
        default_data = pd.DataFrame([
            {"Description": "Materials (Paint, Tile, Wood)", "Material Cost": 0.00, "Labor Hours": 0.0, "Hourly Rate": 50.00},
            {"Description": "Labor - Prep Work", "Material Cost": 0.00, "Labor Hours": 0.0, "Hourly Rate": 50.00},
        ])
        
        # UPDATED: Replaced use_container_width=True with width="stretch"
        edited_df = st.data_editor(default_data, num_rows="dynamic", width="stretch")

        # Calculations
        edited_df['Line Total'] = edited_df['Material Cost'] + (edited_df['Labor Hours'] * edited_df['Hourly Rate'])
        raw_subtotal = edited_df['Line Total'].sum()

        st.divider()
        
        c1, c2, c3 = st.columns(3)
        with c1:
            markup_pct = st.number_input("Overhead/Markup %", min_value=0.0, value=15.0, step=5.0)
        with c2:
            tax_pct = st.number_input("Tax Rate %", min_value=0.0, value=0.0, step=0.1)
        
        markup_amt = raw_subtotal * (markup_pct / 100)
        subtotal_with_markup = raw_subtotal + markup_amt
        tax_amt = subtotal_with_markup * (tax_pct / 100)
        final_total = subtotal_with_markup + tax_amt

        with c3:
            st.metric("Estimated Total", f"${final_total:,.2f}")
            st.caption(f"Subtotal: ${raw_subtotal:,.2f} | Markup: ${markup_amt:,.2f} | Tax: ${tax_amt:,.2f}")

        # Actions
        st.write("### Actions")
        
        col_btn1, col_btn2 = st.columns([1, 2])
        
        save_clicked = col_btn1.button("💾 Save Bid to History", type="primary")
        
        if save_clicked:
            if project_name:
                bid_id = save_bid(selected_client_id, project_name, edited_df, raw_subtotal, markup_pct, tax_pct, final_total)
                st.success(f"Bid saved! ID: {bid_id}")
            else:
                st.error("Please enter a Project Name.")

        # Email / PDF Logic
        if project_name and not edited_df.empty:
            client_data = clients[clients['id'] == selected_client_id].iloc[0]
            
            # Generate PDF
            totals = {
                'subtotal': raw_subtotal, 'markup': markup_pct, 'markup_amt': markup_amt,
                'tax': tax_pct, 'tax_amt': tax_amt, 'total': final_total
            }
            pdf_bytes = create_pdf(client_data['name'], project_name, edited_df, totals)
            
            col_btn2.download_button(
                label="📄 Download PDF Quote",
                data=pdf_bytes,
                file_name=f"Quote_{client_data['name']}_{project_name}.pdf",
                mime="application/pdf"
            )

            # Generate Email Link
            email_subject = f"Estimate for {project_name}"
            email_body = f"""Hi {client_data['name']},%0D%0A%0D%0AHere is the estimate for the {project_name}.%0D%0A%0D%0A
            Total Estimate: ${final_total:,.2f}%0D%0A%0D%0A
            Includes materials, labor, and necessary prep work.%0D%0A%0D%0A
            Please let me know if you would like to proceed!"""
            
            st.markdown(f"""
            <a href="mailto:{client_data['email']}?subject={email_subject}&body={email_body}" target="_blank" 
            style="display: inline-block; padding: 0.5em 1em; color: white; background-color: #FF4B4B; border-radius: 5px; text-decoration: none;">
            📧 Click to Email Client
            </a>
            """, unsafe_allow_html=True)

# --- TAB: BID HISTORY ---
elif menu == "Bid History":
    st.header("Past Bids")
    bids = get_bids()
    
    if bids.empty:
        st.info("No bids created yet.")
    else:
        # Filters
        status_filter = st.multiselect("Filter by Status", options=bids['status'].unique(), default=bids['status'].unique())
        filtered_bids = bids[bids['status'].isin(status_filter)]
        
        # UPDATED: Replaced use_container_width=True with width="stretch"
        st.dataframe(
            filtered_bids[['id', 'date_created', 'customer', 'project_name', 'total', 'status']],
            width="stretch"
        )

        st.divider()
        st.subheader("Update Status")
        c1, c2, c3 = st.columns(3)
        with c1:
            bid_to_edit = st.selectbox("Select Bid ID to Update", options=bids['id'])
        with c2:
            new_status = st.selectbox("New Status", ["Draft", "Sent", "Approved", "Declined", "Completed", "Paid"])
        with c3:
            st.write("") # Spacing
            st.write("") 
            if st.button("Update Status"):
                update_bid_status(bid_to_edit, new_status)
                st.success(f"Bid {bid_to_edit} updated to {new_status}")
                st.rerun()