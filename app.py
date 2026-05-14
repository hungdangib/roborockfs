import streamlit as st
import pandas as pd
from database import init_db, authenticate, add_customer, get_customers, get_maintenance_schedule, update_maintenance_status, delete_customer, update_and_cascade_dates
from datetime import datetime
import json
import os
import random

# Cấu hình trang
st.set_page_config(page_title="Roborock Maintenance Dashboard", layout="wide", page_icon="🤖")

# Custom CSS cho giao diện hiện đại
st.markdown("""
<style>
    .main {
        background-color: #f8fafc;
    }
    .stButton>button {
        background-color: #ef4444;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 24px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #dc2626;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        text-align: center;
    }
    h1, h2, h3 {
        color: #1e293b;
    }
</style>
""", unsafe_allow_html=True)

# Khởi tạo DB nếu chưa có
init_db()

SESSION_FILE = "local_session.json"

# State quản lý đăng nhập
if 'logged_in' not in st.session_state:
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f:
                session_data = json.load(f)
                st.session_state['logged_in'] = True
                st.session_state['user_id'] = session_data.get('user_id')
                st.session_state['role'] = session_data.get('role')
        except:
            st.session_state['logged_in'] = False
    else:
        st.session_state['logged_in'] = False

def login_page():
    st.markdown("<h1 style='text-align: center;'>Đăng nhập Hệ thống</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Tên đăng nhập")
            password = st.text_input("Mật khẩu", type="password")
            submit = st.form_submit_button("Đăng nhập", use_container_width=True)
            
            if submit:
                user = authenticate(username, password)
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['user_id'] = user[0]
                    st.session_state['role'] = user[1]
                    
                    with open(SESSION_FILE, "w") as f:
                        json.dump({"user_id": user[0], "role": user[1]}, f)
                        
                    st.rerun()
                else:
                    st.error("Tên đăng nhập hoặc mật khẩu không đúng!")

def upload_page():
    st.header("Upload Dữ liệu Khách hàng")
    st.write("Tải lên file dữ liệu (CSV hoặc Excel) chứa thông tin khách hàng mua sản phẩm Roborock.")
    
    st.markdown("### Thiết lập bộ lọc Sản phẩm")
    
    # Load cấu hình cũ nếu có
    config_file = 'config.json'
    default_include = "Qrevo, S8, S7, Robot, Dyad, Flexi"
    default_exclude = "phụ kiện, nước lau, chổi, giẻ, rác, dock"
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                default_include = config.get('include', default_include)
                default_exclude = config.get('exclude', default_exclude)
        except:
            pass
            
    include_keywords_input = st.text_input("Tên khớp sản phẩm (ngăn cách bằng dấu phẩy, để trống nếu lấy tất cả):", default_include)
    exclude_keywords_input = st.text_input("Từ khóa bị loại trừ (ngăn cách bằng dấu phẩy):", default_exclude)
    
    st.markdown("---")
    
    uploaded_files = st.file_uploader("Vui lòng chọn một hoặc nhiều file CSV/Excel", type=['csv', 'xlsx', 'xls'], accept_multiple_files=True, key="multi_file_uploader")
    
    if uploaded_files:
        try:
            dfs = []
            for uploaded_file in uploaded_files:
                df_temp = None
                header = uploaded_file.read(4)
                uploaded_file.seek(0)
                
                if header == b'PK\x03\x04' or uploaded_file.name.endswith(('.xlsx', '.xls')):
                    try:
                        if uploaded_file.name.endswith('.xls'):
                            df_temp = pd.read_excel(uploaded_file, engine='xlrd')
                        else:
                            df_temp = pd.read_excel(uploaded_file, engine='openpyxl')
                    except Exception as e:
                        df_temp = pd.read_excel(uploaded_file)
                else:
                    try:
                        df_temp = pd.read_csv(uploaded_file, encoding='utf-8', sep=None, engine='python', on_bad_lines='skip')
                    except UnicodeDecodeError:
                        uploaded_file.seek(0)
                        try:
                            df_temp = pd.read_csv(uploaded_file, encoding='cp1252', sep=None, engine='python', on_bad_lines='skip')
                        except UnicodeDecodeError:
                            uploaded_file.seek(0)
                            try:
                                df_temp = pd.read_csv(uploaded_file, encoding='latin1', sep=None, engine='python', on_bad_lines='skip')
                            except Exception as e:
                                st.error(f"Không thể đọc file {uploaded_file.name} do lỗi định dạng hoặc encoding.")
                                continue
                
                if df_temp is not None and not df_temp.empty:
                    dfs.append(df_temp)
                
            if not dfs:
                st.warning("Không có dữ liệu hợp lệ nào được tải lên.")
                return
                
            df = pd.concat(dfs, ignore_index=True)
            st.success(f"Đọc thành công {len(uploaded_files)} file!")
            st.dataframe(df)
            
            st.markdown("---")
            
            if st.button("Xử lý dữ liệu"):
                # Lưu lại cấu hình mới
                try:
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            'include': include_keywords_input,
                            'exclude': exclude_keywords_input
                        }, f, ensure_ascii=False)
                except Exception as e:
                    print(f"Error saving config: {e}")
                    
                with st.spinner('Đang xử lý dữ liệu...'):
                    # Mapping các cột (Giả định theo mô tả)
                    # Ngày xuất bán, Địa chỉ khách hàng, Tên sản phẩm, Đơn giá bán lẻ, Số điện thoại, Tên khách hàng
                    
                    # Tìm các cột tương ứng (vì file CSV có thể khác biệt chút về tên)
                    cols = df.columns.tolist()
                    
                    date_col = next((c for c in cols if 'ngày xuất' in c.lower() or 'ngày bán' in c.lower() or 'date' in c.lower()), None)
                    addr_col = next((c for c in cols if 'địa chỉ' in c.lower() or 'address' in c.lower()), None)
                    prod_col = next((c for c in cols if 'sản phẩm' in c.lower() or 'tên hàng' in c.lower() or 'product' in c.lower()), None)
                    price_col = next((c for c in cols if 'đơn giá' in c.lower() or 'doanh thu' in c.lower() or 'price' in c.lower() or 'tiền' in c.lower()), None)
                    phone_col = next((c for c in cols if 'điện thoại' in c.lower() or 'phone' in c.lower() or 'sđt' in c.lower()), None)
                    
                    # Ưu tiên các cột tên chính xác
                    name_col = next((c for c in cols if 'tên khách hàng' in c.lower() or 'tên người mua' in c.lower() or 'họ tên' in c.lower()), None)
                    if not name_col:
                        name_col = next((c for c in cols if ('khách hàng' in c.lower() and 'mã' not in c.lower() and 'nhóm' not in c.lower() and 'loại' not in c.lower()) or ('name' in c.lower() and 'product' not in c.lower())), None)
                    
                    code_col = next((c for c in cols if 'imei' in c.lower() or 'serial' in c.lower() or 'sêri' in c.lower()), None)
                    
                    if not all([date_col, prod_col, phone_col, name_col]):
                        st.error("Không tìm thấy đủ các cột yêu cầu trong file CSV. Vui lòng kiểm tra lại cấu trúc.")
                        st.write(f"Tìm thấy: Ngày ({date_col}), Địa chỉ ({addr_col}), SP ({prod_col}), Giá ({price_col}), ĐT ({phone_col}), Tên ({name_col})")
                        return
                    
                    added_count = 0
                    for index, row in df.iterrows():
                        try:
                            # Lấy danh sách từ khóa
                            include_kw = [k.strip().lower() for k in include_keywords_input.split(',') if k.strip()]
                            exclude_kw = [k.strip().lower() for k in exclude_keywords_input.split(',') if k.strip()]
                            
                            prod_name = str(row[prod_col]).lower()
                            if pd.isna(row[prod_col]) or prod_name == 'none' or prod_name == 'nan':
                                continue
                                
                            # 1. Loại trừ trước
                            is_excluded = False
                            for kw in exclude_kw:
                                if kw in prod_name:
                                    is_excluded = True
                                    break
                            if is_excluded:
                                continue
                                
                            # 2. Khớp từ khóa bao gồm
                            if include_kw:
                                is_included = False
                                for kw in include_kw:
                                    if kw in prod_name:
                                        is_included = True
                                        break
                                if not is_included:
                                    continue
                                
                            # Làm sạch giá tiền để lưu vào DB
                            price = 0.0
                            if price_col and price_col in row and not pd.isna(row[price_col]):
                                price_str = str(row[price_col]).replace(',', '').replace('.', '').replace('₫', '').replace('VND', '').strip()
                                try:
                                    price = float(price_str)
                                except ValueError:
                                    pass
                                
                            address = str(row[addr_col]) if addr_col and addr_col in row else "Không có"
                            
                            # Chuyển đổi định dạng ngày nếu cần (Giả định dd-mm-yyyy -> yyyy-mm-dd)
                            raw_date = str(row[date_col]).strip()
                            try:
                                parsed_date = pd.to_datetime(raw_date, dayfirst=True).strftime('%Y-%m-%d')
                            except:
                                parsed_date = datetime.today().strftime('%Y-%m-%d') # Fallback
                            
                            # Lấy mã IMEI (nếu có)
                            imei = str(row[code_col]).strip() if code_col and not pd.isna(row[code_col]) else None
                            
                            success = add_customer(
                                name=str(row[name_col]),
                                phone=str(row[phone_col]),
                                address=address,
                                lat=None,
                                lng=None,
                                product_name=str(row[prod_col]),
                                price=price,
                                purchase_date=parsed_date,
                                imei=imei
                            )
                            
                            # Nếu add_customer trả về False tức là bị trùng IMEI
                            if success is not False:
                                added_count += 1
                        except Exception as e:
                            print(f"Error parsing row {index}: {e}")
                            
                st.success(f"Hoàn tất! Đã thêm (hoặc cập nhật) {added_count} khách hàng mới vào hệ thống (Đã tự động loại bỏ các khách hàng trùng lặp).")
        except Exception as e:
            st.error(f"Lỗi khi đọc file: {e}")

def get_status_color(maintenance_date):
    today = datetime.today()
    m_date = datetime.strptime(maintenance_date, "%Y-%m-%d")
    diff = (m_date - today).days
    
    if diff < 0:
        return "red", "🔴 Trễ hạn"
    elif diff <= 7 and diff >= 0:
        return "orange", "🟡 Sắp đến hạn"
    else:
        return "green", "🟢 Chưa đến hạn"

def dashboard_page():
    st.header("Dashboard Quản lý Bảo dưỡng")
    
    # Xử lý tự động tính toán ngày (+3 tháng) nếu người dùng vừa edit trên bảng
    editor_state = st.session_state.get("maintenance_editor", {})
    edited_rows = editor_state.get("edited_rows", {})
    
    if edited_rows:
        date_changed = False
        index_to_cid = st.session_state.get("index_to_cid", {})
        
        for row_idx_str, changes in edited_rows.items():
            cid = index_to_cid.get(str(row_idx_str))
            if not cid: continue
            
            # Nếu chỉ click checkbox thì bỏ qua
            if len(changes) == 1 and "Chọn" in changes:
                continue
                
            for col_name, new_val in changes.items():
                if col_name == "Ngày xuất bán":
                    update_and_cascade_dates(cid, "purchase_date", str(new_val))
                    date_changed = True
                elif col_name == "Ngày bảo dưỡng dự kiến":
                    update_and_cascade_dates(cid, "pending", str(new_val))
                    date_changed = True
                elif col_name.startswith("Ngày bảo dưỡng lần "):
                    lan_str = col_name.replace("Ngày bảo dưỡng lần ", "")
                    try:
                        update_and_cascade_dates(cid, "history", str(new_val), int(lan_str))
                        date_changed = True
                    except: pass
        if date_changed:
            del st.session_state["maintenance_editor"]
            st.rerun()
            
    df_schedule = get_maintenance_schedule()
    
    if df_schedule.empty:
        st.info("Chưa có lịch bảo dưỡng nào.")
        return
        
    st.session_state["index_to_cid"] = {str(idx): int(row['id']) for idx, row in df_schedule.iterrows()}
        
    # Thống kê
    col1, col2, col3 = st.columns(3)
    
    today_str = datetime.today().strftime("%Y-%m-%d")
    
    df_schedule['color_code'] = df_schedule['maintenance_date'].apply(lambda x: get_status_color(x)[0])
    df_schedule['status_label'] = df_schedule['maintenance_date'].apply(lambda x: get_status_color(x)[1])
    
    green_count = len(df_schedule[df_schedule['color_code'] == 'green'])
    yellow_count = len(df_schedule[df_schedule['color_code'] == 'orange'])
    red_count = len(df_schedule[df_schedule['color_code'] == 'red'])
    
    col1.markdown(f"<div class='metric-card'><h3 style='color: green;'>Chưa đến hạn</h3><h1>{green_count}</h1></div>", unsafe_allow_html=True)
    col2.markdown(f"<div class='metric-card'><h3 style='color: orange;'>Sắp đến/Trễ hạn</h3><h1>{yellow_count}</h1></div>", unsafe_allow_html=True)
    col3.markdown(f"<div class='metric-card'><h3 style='color: red;'>Quá hạn</h3><h1>{red_count}</h1></div>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.subheader("Danh sách Khách hàng cần Bảo dưỡng")
    
    # Bộ lọc địa chỉ
    search_term = st.text_input("🔍 Lọc theo Địa chỉ (Nhập từ khóa như Quận 7, Q7, Nhà Bè...):", "")
    
    # Chọn tất cả
    select_all = st.checkbox("☑️ Chọn tất cả các dòng đang hiển thị")
    
    # Hiển thị bảng
    cols_to_show = ['name', 'phone', 'address', 'product_name', 'status_label', 'maintenance_date', 'purchase_date']
    lan_cols = [c for c in df_schedule.columns if c.startswith('Ngày bảo dưỡng lần')]
    cols_to_show.extend(lan_cols)
    
    display_df = df_schedule[cols_to_show].copy()
    
    if search_term:
        display_df = display_df[display_df['address'].str.contains(search_term, case=False, na=False)]
    
    # Sắp xếp theo ngày bảo dưỡng dự kiến từ gần nhất đến xa nhất
    display_df = display_df.sort_values(by='maintenance_date', ascending=True)
    
    # Thêm cột checkbox Chọn
    display_df.insert(0, "Chọn", select_all)
    
    rename_dict = {
        'name': 'Tên KH',
        'phone': 'SĐT',
        'address': 'Địa chỉ',
        'product_name': 'Sản phẩm',
        'status_label': 'Trạng thái',
        'maintenance_date': 'Ngày bảo dưỡng dự kiến',
        'purchase_date': 'Ngày xuất bán'
    }
    display_df.rename(columns=rename_dict, inplace=True)
    
    # Vô hiệu hóa chỉnh sửa các cột không liên quan
    disabled_cols = ["Tên KH", "SĐT", "Địa chỉ", "Sản phẩm", "Trạng thái"]
    
    edited_df = st.data_editor(
        display_df, 
        use_container_width=True,
        disabled=disabled_cols,
        key="maintenance_editor"
    )
    
    selected_indices = edited_df[edited_df["Chọn"] == True].index
    if not selected_indices.empty:
        st.markdown("---")
        st.markdown(f"### ⚙️ Thao tác cho {len(selected_indices)} khách hàng đã chọn:")
        col1, col2 = st.columns(2)
        
        if col1.button("✅ Xác nhận Đã Bảo Dưỡng", type="primary", use_container_width=True):
            for idx in selected_indices:
                record_id = int(df_schedule.loc[idx, 'record_id'])
                customer_id = int(df_schedule.loc[idx, 'id'])
                update_maintenance_status(record_id, customer_id, today_str)
            del st.session_state["maintenance_editor"]
            st.success("Đã cập nhật thành công! Hệ thống đã tự động tính mốc tiếp theo.")
            st.rerun()
            
        if col2.button("🗑️ Xóa Khách Hàng", use_container_width=True):
            for idx in selected_indices:
                customer_id = int(df_schedule.loc[idx, 'id'])
                delete_customer(customer_id)
            del st.session_state["maintenance_editor"]
            st.success("Đã xóa khách hàng và toàn bộ lịch bảo dưỡng liên quan thành công!")
            st.rerun()

def main():
    if not st.session_state['logged_in']:
        login_page()
    else:
        with st.sidebar:
            st.image("https://roborock.com.vn/wp-content/uploads/2021/04/logo-roborock.png", width=200)
            st.markdown("### Menu")
            page = st.radio("Chức năng", ["Dashboard", "Upload Dữ liệu"])
            
            st.markdown("---")
            st.write(f"👤 Xin chào, **{st.session_state['role']}**")
            if st.button("Đăng xuất"):
                st.session_state['logged_in'] = False
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                st.rerun()
                
        if page == "Dashboard":
            dashboard_page()
        elif page == "Upload Dữ liệu":
            upload_page()

if __name__ == "__main__":
    main()
