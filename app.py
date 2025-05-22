import json
import os
import csv
from io import StringIO, BytesIO
from datetime import datetime  # Fixed import
from flask import Flask, render_template, request, redirect, send_file, flash, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production!

# Constants
USERS_FILE = 'users.json'
DATA_DIR = 'user_data'  # Directory for user-specific data

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

# Load/Save users functions
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users_data = json.load(f)
            return {int(k): User(int(k), v['username'], v['password']) for k, v in users_data.items()}
    return {}

def save_users(users_dict):
    users_data = {k: {'username': v.username, 'password': v.password} for k, v in users_dict.items()}
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)

# Initialize users
users = load_users()
if not users:  # Create admin if no users exist
    users[1] = User(1, 'admin', generate_password_hash('admin123'))
    save_users(users)

@login_manager.user_loader
def load_user(user_id):
    return users.get(int(user_id))

def get_user_data_file(user_id):
    """Get the data file path for a specific user"""
    return os.path.join(DATA_DIR, f'user_{user_id}_data.json')

def load_data(user_id):
    """Load medicine data for specific user"""
    data_file = get_user_data_file(user_id)
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            drugs = json.load(f)
            # Convert string dates to date objects and calculate profits
            for drug in drugs:
                if 'expiry_date' in drug and drug['expiry_date']:
                    try:
                        drug['expiry_date_obj'] = datetime.strptime(drug['expiry_date'], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        drug['expiry_date_obj'] = None
                
                # Ensure profit values exist
                if 'purchase_price' in drug and 'retail_price' in drug:
                    drug['retail_profit'] = drug['retail_price'] - drug['purchase_price']
                if 'purchase_price' in drug and 'wholesale_price' in drug:
                    drug['wholesale_profit'] = drug['wholesale_price'] - drug['purchase_price']
            return drugs
    return []

def save_data(user_id, data):
    """Save medicine data for specific user"""
    # Make sure we don't save the temporary date object
    for drug in data:
        if 'expiry_date_obj' in drug:
            del drug['expiry_date_obj']
    data_file = get_user_data_file(user_id)
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/')
@login_required 
def index():
    drugs = load_data(current_user.id)
    query = request.args.get('search', '').lower()
    
    if query:
        filtered = [drug for drug in drugs if query in drug['name'].lower()]
    else:
        filtered = drugs
    
    # Calculate totals like in report route
    total_cost = sum(d['purchase_price'] * d['quantity'] for d in filtered)
    total_retail_profit = sum((d['retail_price'] - d['purchase_price']) * d['quantity'] for d in filtered)
    total_wholesale_profit = sum((d['wholesale_price'] - d['purchase_price']) * d['quantity'] for d in filtered)
    total_profit = total_retail_profit + total_wholesale_profit
    
    return render_template('index.html', 
                         drugs=filtered,
                         total_cost=total_cost,
                         total_profit=total_profit,
                         current_date=datetime.now().date())

@app.route('/add', methods=['POST'])
@login_required 
def add():
    drugs = load_data(current_user.id)
    try:
        name = request.form['name']
        quantity = int(request.form['quantity'])
        purchase_price = float(request.form['purchase_price'])
        retail_price = float(request.form['retail_price'])
        wholesale_price = float(request.form['wholesale_price'])
        expiry_date = request.form['expiry_date']
        
        drugs.append({
            "name": name,
            "quantity": quantity,
            "purchase_price": purchase_price,
            "retail_price": retail_price,
            "wholesale_price": wholesale_price,
            "retail_profit": retail_price - purchase_price,  # Explicit calculation
            "wholesale_profit": wholesale_price - purchase_price,  # Explicit calculation
            "expiry_date": expiry_date
        })

        save_data(current_user.id, drugs)
        flash('تمت إضافة الدواء بنجاح!', 'success')
    except Exception as e:
        flash(f'حدث خطأ أثناء إضافة الدواء: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/delete/<int:index>')
@login_required 
def delete(index):
    source = request.args.get('source', 'index')  # Get source parameter
    drugs = load_data(current_user.id)
    
    if 0 <= index < len(drugs):
        drugs.pop(index)
        save_data(current_user.id, drugs)
        flash('تم حذف الدواء بنجاح!', 'success')
        
        # Redirect based on source
        if source == 'report':
            return redirect(url_for('report', _=datetime.now().timestamp()))
        return redirect(url_for('index', _=datetime.now().timestamp()))
        
    else:
        flash('الدواء غير موجود', 'error')
        return redirect(url_for('index'))
@app.route('/report')
@login_required 
def report():
    drugs = load_data(current_user.id)
    search_query = request.args.get('search', '').lower()
    low_stock = request.args.get('low_stock') == 'true'

    filtered_drugs = drugs
    if search_query:
        filtered_drugs = [d for d in filtered_drugs if search_query in d['name'].lower()]
    if low_stock:
        filtered_drugs = [d for d in filtered_drugs if d['quantity'] < 10]

    total_medicines = len(filtered_drugs)
    total_quantity = sum(d['quantity'] for d in filtered_drugs)
    total_cost = sum(d['purchase_price'] * d['quantity'] for d in filtered_drugs)
    total_retail_revenue = sum(d['retail_price'] * d['quantity'] for d in filtered_drugs)
    total_wholesale_revenue = sum(d['wholesale_price'] * d['quantity'] for d in filtered_drugs)
    total_retail_profit = sum((d['retail_price'] - d['purchase_price']) * d['quantity'] for d in filtered_drugs)
    total_wholesale_profit = sum((d['wholesale_price'] - d['purchase_price']) * d['quantity'] for d in filtered_drugs)
    
    # Calculate total profit (retail + wholesale)
    total_profit = total_retail_profit + total_wholesale_profit

    return render_template('report.html',
                         drugs=filtered_drugs,
                         total_medicines=total_medicines,
                         total_quantity=total_quantity,
                         total_cost=total_cost,
                         total_retail_revenue=total_retail_revenue,
                         total_wholesale_revenue=total_wholesale_revenue,
                         total_retail_profit=total_retail_profit,
                         total_wholesale_profit=total_wholesale_profit,
                         total_profit=total_profit,  # Add this line
                         search_query=search_query,
                         low_stock=low_stock,
                         current_date=datetime.now().date())

@app.route('/export')
@login_required 
def export():
    drugs = load_data(current_user.id)
    # Write CSV to a text buffer
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['الدواء', 'الكمية', 'سعر الشراء', 'سعر المفرد', 'ربح المفرد', 'سعر الجملة', 'ربح الجملة', 'تاريخ الانتهاء'])

    for drug in drugs:
        cw.writerow([
            drug['name'],
            drug['quantity'],
            drug['purchase_price'],
            drug['retail_price'],
            drug.get('retail_profit', 0),
            drug['wholesale_price'],
            drug.get('wholesale_profit', 0),
            drug.get('expiry_date', '')
        ])

    # Convert to binary for download
    output = BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name='تقرير_المخزون.csv'
    )

@app.route('/edit/<int:index>', methods=['GET', 'POST'])
@login_required 
def edit(index):
    source = request.args.get('source', 'index')  # Get source parameter
    drugs = load_data(current_user.id)
    
    if 0 <= index < len(drugs):
        drug = drugs[index]
        if request.method == 'POST':
            try:
                drug['name'] = request.form['name']
                drug['quantity'] = int(request.form['quantity'])
                drug['purchase_price'] = float(request.form['purchase_price'])
                drug['retail_price'] = float(request.form['retail_price'])
                drug['wholesale_price'] = float(request.form['wholesale_price'])
                drug['expiry_date'] = request.form['expiry_date']
                # Update profits
                drug['retail_profit'] = drug['retail_price'] - drug['purchase_price']
                drug['wholesale_profit'] = drug['wholesale_price'] - drug['purchase_price']
                
                save_data(current_user.id, drugs)
                flash('تم تحديث بيانات الدواء بنجاح!', 'success')
                
                # Redirect based on source
                if source == 'report':
                    return redirect(url_for('report', _=datetime.now().timestamp()))
                return redirect(url_for('index', _=datetime.now().timestamp()))
                
            except Exception as e:
                flash(f'حدث خطأ أثناء التحديث: {str(e)}', 'error')
                return redirect(url_for('index'))

        return render_template('edit.html', drug=drug, index=index, source=source)
    else:
        flash('الدواء غير موجود', 'error')
        return redirect(url_for('index'))
    
@app.route('/sell/<int:index>', methods=['POST'])
@login_required 
def sell(index):
    drugs = load_data(current_user.id)
    if 0 <= index < len(drugs):
        try:
            sell_qty = int(request.form['sell_quantity'])
            if 0 < sell_qty <= drugs[index]['quantity']:
                drugs[index]['quantity'] -= sell_qty
                save_data(current_user.id, drugs)
                flash(f'تم بيع {sell_qty} وحدة بنجاح!', 'success')
            else:
                flash('الكمية المطلوبة غير متوفرة أو غير صالحة', 'error')
        except ValueError:
            flash('الكمية المدخلة غير صالحة', 'error')
    else:
        flash('الدواء غير موجود', 'error')
    return redirect(url_for('index'))

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = next((u for u in users.values() if u.username == username), None)
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validation
        if len(password) < 8:
            flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'error')
        elif password != confirm_password:
            flash('كلمة المرور غير متطابقة', 'error')
        elif any(u.username == username for u in users.values()):
            flash('اسم المستخدم موجود مسبقاً', 'error')
        else:
            # Create new user
            new_id = max(users.keys()) + 1 if users else 1
            users[new_id] = User(new_id, username, generate_password_hash(password))
            save_users(users)
            flash('تم إنشاء الحساب بنجاح! يرجى تسجيل الدخول', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('login'))
def migrate_data():
    for user_id in users:
        drugs = load_data(user_id)
        for drug in drugs:
            if 'retail_price' in drug and 'purchase_price' in drug:
                drug['retail_profit'] = drug['retail_price'] - drug['purchase_price']
            if 'wholesale_price' in drug and 'purchase_price' in drug:
                drug['wholesale_profit'] = drug['wholesale_price'] - drug['purchase_price']
        save_data(user_id, drugs)

# Run this once
migrate_data()
if __name__ == '__main__':
    app.run(debug=True)