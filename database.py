import sqlite3
import pandas as pd
from datetime import datetime, timedelta

DB_NAME = "roborock.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Bảng Khách hàng
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        address TEXT,
        lat REAL,
        lng REAL,
        product_name TEXT,
        price REAL,
        purchase_date DATE,
        ma_hang TEXT,
        imei TEXT,
        last_maintenance_date DATE
    )
    ''')
    
    # Đảm bảo bảng customers có cột ma_hang (trong trường hợp DB đã tạo từ trước)
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN ma_hang TEXT")
    except sqlite3.OperationalError:
        pass # Cột đã tồn tại
        
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN imei TEXT")
    except sqlite3.OperationalError:
        pass # Cột đã tồn tại
        
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN last_maintenance_date DATE")
    except sqlite3.OperationalError:
        pass # Cột đã tồn tại
        
    
    # Bảng Lịch sử bảo dưỡng
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS maintenance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        maintenance_date DATE,
        status TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    ''')
    
    # Bảng Người dùng (Đăng nhập)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    ''')
    
    # Tạo user mặc định
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('staff', 'staff123', 'staff')")
        
    conn.commit()
    conn.close()

def authenticate(username, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, role FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

def customer_exists(imei):
    if not imei or pd.isna(imei):
        return False
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM customers WHERE imei = ?", (imei,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_customer(name, phone, address, lat, lng, product_name, price, purchase_date, imei=None):
    if imei and customer_exists(imei):
        return False # Đã tồn tại
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO customers (name, phone, address, lat, lng, product_name, price, purchase_date, imei)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, phone, address, lat, lng, product_name, price, purchase_date, imei))
    customer_id = cursor.lastrowid
    
    # Tạo lịch bảo dưỡng lần đầu (mốc 3 tháng)
    next_date = datetime.strptime(purchase_date, "%Y-%m-%d") + timedelta(days=90)
    cursor.execute('''
    INSERT INTO maintenance_records (customer_id, maintenance_date, status)
    VALUES (?, ?, ?)
    ''', (customer_id, next_date.strftime("%Y-%m-%d"), 'pending'))
    
    conn.commit()
    conn.close()

def get_customers():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM customers", conn)
    conn.close()
    return df

def get_maintenance_schedule():
    conn = sqlite3.connect(DB_NAME)
    query = '''
    SELECT c.id, c.name, c.phone, c.address, c.lat, c.lng, c.product_name, c.purchase_date, c.last_maintenance_date,
           m.id as record_id, m.maintenance_date, m.status
    FROM customers c
    JOIN maintenance_records m ON c.id = m.customer_id
    WHERE m.status = 'pending'
    ORDER BY m.maintenance_date ASC
    '''
    df = pd.read_sql_query(query, conn)
    
    query_history = "SELECT customer_id, maintenance_date FROM maintenance_records WHERE status = 'completed' ORDER BY maintenance_date ASC"
    df_hist = pd.read_sql_query(query_history, conn)
    conn.close()
    
    hist_dict = {}
    for _, row in df_hist.iterrows():
        cid = row['customer_id']
        if cid not in hist_dict:
            hist_dict[cid] = []
        hist_dict[cid].append(row['maintenance_date'])
        
    max_len = max([len(v) for v in hist_dict.values()]) if hist_dict else 0
    for i in range(1, max_len + 1):
        df[f'Ngày bảo dưỡng lần {i}'] = df['id'].apply(lambda x: hist_dict.get(x, [])[i-1] if x in hist_dict and len(hist_dict[x]) >= i else None)
        
    return df

def update_maintenance_status(record_id, customer_id, current_date):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Đánh dấu đã hoàn thành và cập nhật ngày bảo dưỡng thực tế
    cursor.execute("UPDATE maintenance_records SET status = 'completed', maintenance_date = ? WHERE id = ?", (current_date, record_id))
    
    # Cập nhật ngày bảo dưỡng gần nhất cho khách hàng
    cursor.execute("UPDATE customers SET last_maintenance_date = ? WHERE id = ?", (current_date, customer_id))
    
    # Tính mốc tiếp theo
    purchase_date_str = cursor.execute("SELECT purchase_date FROM customers WHERE id = ?", (customer_id,)).fetchone()[0]
    purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
    
    # Check if 2 years have passed
    two_years_later = purchase_date + timedelta(days=730)
    next_date = datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=90)
    
    if next_date <= two_years_later:
        cursor.execute('''
        INSERT INTO maintenance_records (customer_id, maintenance_date, status)
        VALUES (?, ?, ?)
        ''', (customer_id, next_date.strftime("%Y-%m-%d"), 'pending'))
        
    conn.commit()
    conn.close()

def update_and_cascade_dates(customer_id, field_changed, new_date_str, lan_index=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    records = cursor.execute("SELECT id, status FROM maintenance_records WHERE customer_id = ? ORDER BY id ASC", (customer_id,)).fetchall()
    
    try:
        if field_changed == 'purchase_date':
            cursor.execute("UPDATE customers SET purchase_date = ? WHERE id = ?", (new_date_str, customer_id))
            current_date = datetime.strptime(new_date_str, "%Y-%m-%d")
            for rec in records:
                current_date += timedelta(days=90)
                cursor.execute("UPDATE maintenance_records SET maintenance_date = ? WHERE id = ?", (current_date.strftime("%Y-%m-%d"), rec[0]))
                
        elif field_changed == 'history':
            if lan_index is not None and lan_index - 1 < len(records):
                current_date = datetime.strptime(new_date_str, "%Y-%m-%d")
                cursor.execute("UPDATE maintenance_records SET maintenance_date = ? WHERE id = ?", (current_date.strftime("%Y-%m-%d"), records[lan_index-1][0]))
                for i in range(lan_index, len(records)):
                    current_date += timedelta(days=90)
                    cursor.execute("UPDATE maintenance_records SET maintenance_date = ? WHERE id = ?", (current_date.strftime("%Y-%m-%d"), records[i][0]))
                    
        elif field_changed == 'pending':
            cursor.execute("UPDATE maintenance_records SET maintenance_date = ? WHERE customer_id = ? AND status = 'pending'", (new_date_str, customer_id))
    except Exception as e:
        print("Date parse error:", e)
        
    conn.commit()
    conn.close()

def delete_customer(customer_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Xóa lịch bảo dưỡng của khách hàng này trước
    cursor.execute("DELETE FROM maintenance_records WHERE customer_id = ?", (customer_id,))
    # Xóa khách hàng
    cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
