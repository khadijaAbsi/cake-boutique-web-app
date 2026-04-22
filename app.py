from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from MySQLdb.cursors import DictCursor
import datetime
import os
from werkzeug.utils import secure_filename
import MySQLdb.cursors  
from flask_moment import moment
app = Flask(__name__)
app.secret_key = 'your_secret_key_here' 
app.jinja_env.globals['datetime'] = datetime  

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '0195'  
app.config['MYSQL_DB'] = 'cakeShop'

mysql = MySQL(app)
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.datetime.now().year}

UPLOAD_FOLDER = 'static/uploads/cakes' 
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} 
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes for common pages ---
@app.route('/')
def index():
    return redirect(url_for('home'))

@app.route('/home')
def home():
    return render_template('home.html')

# --- User Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'employee_id' in session or 'customer_id' in session:
        flash('You are already logged in!', 'info')
        # Redirect based on existing session type if already logged in
        if 'employee_id' in session:
            return redirect(url_for('dashboard'))
        else: # customer_id in session
            return redirect(url_for('home'))

    if request.method == 'POST':
        user_type = request.form['user_type']
        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor(DictCursor)
        user = None

        if user_type == 'employee':
            cur.execute("SELECT Emp_id, Emp_name, Pos, password, is_manager FROM Employee WHERE email = %s", (email,))
            user = cur.fetchone()
            if user and check_password_hash(user['password'], password):
                session['employee_id'] = user['Emp_id']
                session['username'] = user['Emp_name']
                session['position'] = user['Pos']
                session['is_manager'] = user['is_manager']
                flash('Logged in successfully as Employee!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Incorrect email or password for Employee.', 'danger')
        elif user_type == 'customer':
            cur.execute("SELECT customer_id, name, password FROM Customer WHERE email = %s", (email,))
            user = cur.fetchone()
            if user and check_password_hash(user['password'], password):
                session['customer_id'] = user['customer_id']
                session['username'] = user['name'] 
                flash('Logged in successfully as Customer!', 'success')
                return redirect(url_for('home')) 
            else:
                flash('Incorrect email or password for Customer.', 'danger')
        cur.close()
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'employee_id' in session or 'customer_id' in session:
        flash('You are already logged in!', 'info')
        if 'employee_id' in session:
            return redirect(url_for('dashboard'))
        else:
            return redirect(url_for('home'))

    if request.method == 'POST':
        user_type = request.form['user_type']
        username = request.form['username'] 
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        cur = mysql.connection.cursor(DictCursor)
        try:
            if user_type == 'customer':
                # التحقق مما إذا كان البريد الإلكتروني موجودًا بالفعل
                cur.execute("SELECT COUNT(*) FROM Customer WHERE email = %s", (email,))
                if cur.fetchone()['COUNT(*)'] > 0:
                    flash('Email already registered as a customer.', 'danger')
                    return render_template('signup.html')
                cur.execute("INSERT INTO Customer (name, email, password, registration_date) VALUES (%s, %s, %s, CURDATE())",
                            (username, email, hashed_password))
                mysql.connection.commit()
                flash('Customer account created successfully! Please login.', 'success')
                return redirect(url_for('login'))
            

        except MySQLdb.Error as e:
            flash(f"Error during signup: {e}", 'danger')
            mysql.connection.rollback()
        finally:
            cur.close()

    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.pop('employee_id', None)
    session.pop('customer_id', None)
    session.pop('username', None)
    session.pop('position', None)
    session.pop('is_manager', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# --- Employee Dashboard & Management ---
@app.route('/dashboard')
def dashboard():
    if 'employee_id' not in session:
        flash('Employee login required to access dashboard', 'danger')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(DictCursor)

    # Fetch recent orders (example: last 10 orders)
    cur.execute("""
        SELECT o.order_id, c.name AS customer_name, o.order_date, o.status, o.total_amount
        FROM `Order` o
        JOIN Customer c ON o.customer_id = c.customer_id
        ORDER BY o.order_date DESC, o.order_time DESC
        LIMIT 10
    """)
    recent_orders = cur.fetchall()

    # Fetch low stock ingredients (example: stock_level < 10)
    cur.execute("SELECT name, stock_level FROM Ingredient WHERE stock_level < 10 ORDER BY stock_level ASC")
    low_stock = cur.fetchall()

    cur.close()
    return render_template('dashboard.html', recent_orders=recent_orders, low_stock=low_stock)

# --- Cake Management ---
@app.route('/manage_cakes')
def manage_cakes():
     
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager login required to manage cakes.', 'danger')
        return redirect(url_for('login'))

    cur = None
    cakes = []
    try:
        
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 
        cur.execute("SELECT cake_id, name, description, price, stock, category, image_url, popularity, available FROM Cake")
        cakes = cur.fetchall()
    except Exception as e:
        flash(f"Error fetching cakes: {e}", 'danger')
        print(f"Database error in manage_cakes(): {e}")
    finally:
        if cur:
            cur.close()
    
    return render_template('manage_cakes.html', cakes=cakes)

@app.route('/add_cake', methods=['GET', 'POST'])
def add_cake():
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager login required to add cakes.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category = request.form.get('category')
        popularity = int(request.form.get('popularity', 50))
        available = 'available' in request.form 

        image_url = None 


        if 'image_file' in request.files:
            file = request.files['image_file']
            # إذا لم يقم المستخدم بتحديد ملف، فسيقوم المتصفح بإرسال جزء فارغ بدون اسم ملف.
            if file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename) # تأمين اسم الملف
                
                # بناء المسار الكامل لحفظ الملف
                # app.root_path هو مسار مجلد التطبيق الرئيسي (حيث يوجد app.py)
                upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
                
                # إنشاء المجلد إذا لم يكن موجودًا
                os.makedirs(upload_path, exist_ok=True)
                
                # حفظ الملف
                file.save(os.path.join(upload_path, filename))
                
                # تخزين المسار النسبي الذي يمكن الوصول إليه من الويب
                
                image_url = '/' + os.path.join(app.config['UPLOAD_FOLDER'], filename).replace('\\', '/')
            elif file.filename != '' and not allowed_file(file.filename):
                flash('Invalid file type! Allowed types are png, jpg, jpeg, gif.', 'danger')
                return render_template('add_cake.html', **request.form) # إعادة تعبئة النموذج

        # ================================================================

        if not name or not price or not stock:
            flash('Name, Price, and Stock are required!', 'danger')
            return render_template('add_cake.html', **request.form) # لإعادة تعبئة البيانات المدخلة
        else:
            cur = None
            try:
                cur = mysql.connection.cursor()
                cur.execute(
                    "INSERT INTO Cake (name, description, price, stock, category, image_url, popularity, available) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (name, description, price, stock, category, image_url, popularity, available)
                )
                mysql.connection.commit()
                flash('Cake added successfully!', 'success')
                return redirect(url_for('manage_cakes'))
            except Exception as e:
                mysql.connection.rollback()
                flash(f'Error adding cake: {e}', 'danger')
                print(f"Database error in add_cake(): {e}")
            finally:
                if cur:
                    cur.close()
    return render_template('add_cake.html')

@app.route('/edit_cake/<int:cake_id>', methods=['GET', 'POST'])
def edit_cake(cake_id):
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager login required to edit cakes.', 'danger')
        return redirect(url_for('login'))

    cur = None
    cake = None
    try:
        cur = mysql.connection.cursor()
        if request.method == 'POST':
            name = request.form['name']
            description = request.form.get('description')
            price = float(request.form['price'])
            stock = int(request.form['stock'])
            category = request.form.get('category')
            popularity = int(request.form.get('popularity', 50))
            available = 'available' in request.form

            # استرجاع الصورة الحالية قبل التعديل
            cur.execute("SELECT image_url FROM Cake WHERE cake_id = %s", (cake_id,))
            current_image_url = cur.fetchone()['image_url'] if cur.rowcount > 0 else None

            image_url = current_image_url # افتراضيًا، احتفظ بالصورة الحالية

            # ================================================================
            #               التعامل مع تحميل الملفات في التعديل
            # ================================================================
            if 'image_file' in request.files:
                file = request.files['image_file']
                if file.filename != '' and allowed_file(file.filename):
                    
                    if current_image_url and current_image_url != '/' + os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename)).replace('\\','/'):
                        old_filepath = os.path.join(app.root_path, current_image_url[1:].replace('/', os.sep))
                        if os.path.exists(old_filepath):
                            os.remove(old_filepath)
                            
                    filename = secure_filename(file.filename)
                    upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
                    os.makedirs(upload_path, exist_ok=True)
                    file.save(os.path.join(upload_path, filename))
                    image_url = '/' + os.path.join(app.config['UPLOAD_FOLDER'], filename).replace('\\', '/')
                elif file.filename != '' and not allowed_file(file.filename):
                    flash('Invalid file type! Allowed types are png, jpg, jpeg, gif.', 'danger')
                    # استرجع بيانات الكعكة لعرض النموذج مرة أخرى
                    cur.execute("SELECT * FROM Cake WHERE cake_id = %s", (cake_id,))
                    cake = cur.fetchone()
                    return render_template('edit_cake.html', cake=cake)
            
            


            
            if 'remove_image' in request.form and request.form['remove_image'] == 'true':
                if current_image_url:
                    old_filepath = os.path.join(app.root_path, current_image_url[1:].replace('/', os.sep))
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                image_url = None # تعيين image_url إلى None في قاعدة البيانات
            # ================================================================

            if not name or not price or not stock:
                flash('Name, Price, and Stock are required!', 'danger')
                # استرجع بيانات الكعكة لعرض النموذج مرة أخرى
                cur.execute("SELECT * FROM Cake WHERE cake_id = %s", (cake_id,))
                cake = cur.fetchone()
                return render_template('edit_cake.html', cake=cake)
            else:
                cur.execute(
                    "UPDATE Cake SET name=%s, description=%s, price=%s, stock=%s, category=%s, image_url=%s, popularity=%s, available=%s WHERE cake_id=%s",
                    (name, description, price, stock, category, image_url, popularity, available, cake_id)
                )
                mysql.connection.commit()
                flash('Cake updated successfully!', 'success')
                return redirect(url_for('manage_cakes'))
        else: # GET request
            cur.execute("SELECT * FROM Cake WHERE cake_id = %s", (cake_id,))
            cake = cur.fetchone()
            if not cake:
                flash('Cake not found!', 'danger')
                return redirect(url_for('manage_cakes'))
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error processing cake: {e}', 'danger')
        print(f"Database error in edit_cake(): {e}")
    finally:
        if cur:
            cur.close()
    return render_template('edit_cake.html', cake=cake)






@app.route('/delete_cake/<int:cake_id>', methods=['POST'])
def delete_cake(cake_id):
    # This ensures only managers can delete cakes
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager login required to delete cakes.', 'danger')
        return redirect(url_for('login'))

    cur = None
    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 
        
        # Optionally, fetch image_url to delete the associated image file
        cur.execute("SELECT image_url FROM Cake WHERE cake_id = %s", (cake_id,))
        cake_image_url = cur.fetchone()['image_url'] if cur.rowcount > 0 else None

        cur.execute("DELETE FROM Cake WHERE cake_id = %s", (cake_id,))
        mysql.connection.commit()

        # Delete the image file from the server if it exists
        if cake_image_url:
            filepath_to_delete = os.path.join(app.root_path, cake_image_url[1:].replace('/', os.sep))
            if os.path.exists(filepath_to_delete):
                os.remove(filepath_to_delete)
                print(f"Deleted image file: {filepath_to_delete}")
            else:
                print(f"Image file not found for deletion: {filepath_to_delete}")

        flash('Cake deleted successfully!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error deleting cake: {e}', 'danger')
        print(f"Database error in delete_cake(): {e}")
    finally:
        if cur:
            cur.close()
    return redirect(url_for('manage_cakes'))
@app.route('/inventory')
def manage_inventory():
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(DictCursor)
    
    # Get all ingredients
    cur.execute("SELECT * FROM Ingredient ORDER BY name")
    ingredients = cur.fetchall()

    # Get recent shipments (adjust LIMIT as needed)
    cur.execute("""
        SELECT sh.shipment_id, i.name AS ingredient_name, s.name AS supplier_name, 
               sh.quantity, sh.shipment_date, e.Emp_name AS employee_name
        FROM Shipments sh
        JOIN Ingredient i ON sh.ingredient_id = i.ingredient_id
        JOIN Supplier s ON sh.supplier_id = s.supplier_id
        LEFT JOIN Employee e ON sh.employee_id = e.Emp_id
        ORDER BY sh.shipment_date DESC, sh.shipment_id DESC
        LIMIT 5
    """)
    recent_shipments = cur.fetchall()

    cur.close()
    return render_template('inventory.html', ingredients=ingredients, shipments=recent_shipments)

@app.route('/add_ingredient', methods=['GET', 'POST'])
def add_ingredient():
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        unit = request.form.get('unit')
        stock_level = float(request.form['stock_level'])

        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO Ingredient (name, stock_level, Unit) VALUES (%s, %s, %s)",
                        (name, stock_level, unit))
            mysql.connection.commit()
            flash('Ingredient added successfully!', 'success')
            return redirect(url_for('manage_inventory'))
        except MySQLdb.Error as e:
            flash(f"Error adding ingredient: {e}", 'danger')
            mysql.connection.rollback()
        finally:
            cur.close()
    return render_template('add_ingredient.html')

@app.route('/update_inventory/<int:ingredient_id>', methods=['POST'])
def update_inventory(ingredient_id):
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_stock = float(request.form['stock_level'])
        
        cur = mysql.connection.cursor()
        try:
            cur.execute("UPDATE Ingredient SET stock_level = %s WHERE ingredient_id = %s",
                        (new_stock, ingredient_id))
            mysql.connection.commit()
            flash('Stock updated successfully!', 'success')
        except MySQLdb.Error as e:
            flash(f"Error updating stock: {e}", 'danger')
            mysql.connection.rollback()
        finally:
            cur.close()
    return redirect(url_for('manage_inventory'))

@app.route('/ship_ingredient', methods=['GET', 'POST'])
def ship_ingredient():
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))
    
    cur = mysql.connection.cursor(DictCursor)
    cur.execute("SELECT ingredient_id, name FROM Ingredient ORDER BY name")
    ingredients = cur.fetchall()
    cur.execute("SELECT supplier_id, name FROM Supplier ORDER BY name")
    suppliers = cur.fetchall()
    cur.close()

    if request.method == 'POST':
        ingredient_id = request.form['ingredient_id']
        supplier_id = request.form['supplier_id']
        quantity = float(request.form['quantity'])
        shipment_date_str = request.form['shipment_date']
        employee_id = session['employee_id'] # Employee making the shipment

        # Convert date string to date object
        shipment_date = datetime.datetime.strptime(shipment_date_str, '%Y-%m-%d').date()

        cur = mysql.connection.cursor()
        try:
            # Insert into Shipments
            cur.execute("""
                INSERT INTO Shipments (ingredient_id, supplier_id, shipment_date, quantity, employee_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (ingredient_id, supplier_id, shipment_date, quantity, employee_id))
            
            # Update ingredient stock level (add quantity)
            cur.execute("UPDATE Ingredient SET stock_level = stock_level + %s WHERE ingredient_id = %s",
                        (quantity, ingredient_id))
            
            mysql.connection.commit()
            flash('Shipment added and inventory updated!', 'success')
            return redirect(url_for('manage_inventory'))
        except MySQLdb.Error as e:
            flash(f"Error adding shipment: {e}", 'danger')
            mysql.connection.rollback()
        finally:
            cur.close()

    return render_template('ship_ingredient.html', ingredients=ingredients, suppliers=suppliers)

@app.route('/view_shipments')
def view_shipments():
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(DictCursor)
    cur.execute("""
        SELECT sh.shipment_id, i.name AS ingredient_name, s.name AS supplier_name, 
               sh.quantity, sh.shipment_date, e.Emp_name AS employee_name
        FROM Shipments sh
        JOIN Ingredient i ON sh.ingredient_id = i.ingredient_id
        JOIN Supplier s ON sh.supplier_id = s.supplier_id
        LEFT JOIN Employee e ON sh.employee_id = e.Emp_id
        ORDER BY sh.shipment_date DESC, sh.shipment_id DESC
    """)
    shipments = cur.fetchall()
    cur.close()

    return render_template('view_shipments.html', shipments=shipments)

@app.route('/inventory/add_ingredient_to_cake/<int:cake_id>', methods=['GET', 'POST'])
def add_ingredient_to_cake(cake_id):
    if 'employee_id' not in session:
        flash('Login required', 'danger')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(DictCursor)

    # Get cake info
    cur.execute("SELECT * FROM Cake WHERE cake_id = %s", (cake_id,))
    cake = cur.fetchone()

    # Get all ingredients
    cur.execute("SELECT ingredient_id, name, Unit FROM Ingredient ORDER BY name")
    ingredients = cur.fetchall()

    # Get existing ingredients for this cake
    cur.execute("SELECT ingredient_id, quantity FROM Cake_Ingredient WHERE cake_id = %s", (cake_id,))
    existing_ingredients_qty = {item['ingredient_id']: item['quantity'] for item in cur.fetchall()}

    if request.method == 'POST':
        for ing in ingredients:
            ing_id = str(ing['ingredient_id'])
            # Use get() with a default to handle unchecked/empty inputs
            qty_str = request.form.get(f'quantity_{ing_id}', '').strip() 
            
            if qty_str: # Only process if quantity is provided
                try:
                    qty = float(qty_str)
                    if qty > 0:
                        cur.execute("""
                            INSERT INTO Cake_Ingredient (cake_id, ingredient_id, quantity)
                            VALUES (%s, %s, %s)
                            ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)
                        """, (cake_id, ing['ingredient_id'], qty))
                    else: # If quantity is 0 or less, consider deleting if it exists
                        cur.execute("DELETE FROM Cake_Ingredient WHERE cake_id = %s AND ingredient_id = %s",
                                    (cake_id, ing['ingredient_id']))
                except ValueError:
                    flash(f"Invalid quantity for {ing['name']}. Please enter a number.", 'danger')
                    mysql.connection.rollback() # Rollback changes if any invalid input
                    cur.close()
                    # Re-fetch data to render correctly after error
                    cur = mysql.connection.cursor(DictCursor)
                    cur.execute("SELECT * FROM Cake WHERE cake_id = %s", (cake_id,))
                    cake = cur.fetchone()
                    cur.execute("SELECT ingredient_id, name, Unit FROM Ingredient ORDER BY name")
                    ingredients = cur.fetchall()
                    cur.execute("SELECT ingredient_id, quantity FROM Cake_Ingredient WHERE cake_id = %s", (cake_id,))
                    existing_ingredients_qty = {item['ingredient_id']: item['quantity'] for item in cur.fetchall()}
                    return render_template('add_ingredient_to_cake.html', cake=cake, ingredients=ingredients, existing_ingredients_qty=existing_ingredients_qty)
            else: # If quantity is empty/not provided, delete if it existed before
                if ing['ingredient_id'] in existing_ingredients_qty:
                    cur.execute("DELETE FROM Cake_Ingredient WHERE cake_id = %s AND ingredient_id = %s",
                                (cake_id, ing['ingredient_id']))
                    
        mysql.connection.commit()
        cur.close()
        flash('Ingredients updated for this cake!', 'success')
        return redirect(url_for('manage_cakes'))
    
    cur.close()
    return render_template('add_ingredient_to_cake.html', cake=cake, ingredients=ingredients, existing_ingredients_qty=existing_ingredients_qty)


# --- Order Management ---
@app.route('/orders')
def manage_orders():
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(DictCursor)
    status_filter = request.args.get('status', 'all')

    query = """
        SELECT o.order_id, c.name AS customer_name, o.order_date, o.status, o.total_amount
        FROM `Order` o
        JOIN Customer c ON o.customer_id = c.customer_id
    """
    params = []
    if status_filter != 'all':
        query += " WHERE o.status = %s"
        params.append(status_filter)
    query += " ORDER BY o.order_date DESC, o.order_time DESC"

    cur.execute(query, params)
    orders = cur.fetchall()
    cur.close()
    return render_template('orders.html', orders=orders, current_status_filter=status_filter)

@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))

    new_status = request.form['status']
    
    cur = mysql.connection.cursor()
    try:
        cur.execute("UPDATE `Order` SET status = %s WHERE order_id = %s", (new_status, order_id))
        mysql.connection.commit()
        flash(f'Order {order_id} status updated to {new_status}!', 'success')
    except MySQLdb.Error as e:
        flash(f"Error updating order status: {e}", 'danger')
        mysql.connection.rollback()
    finally:
        cur.close()
    return redirect(url_for('manage_orders', status=request.args.get('current_status_filter', 'all')))



# --- Employee Management (Manager Only) ---
@app.route('/employees')
def view_employees():
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager access required', 'danger')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(DictCursor)
    cur.execute("SELECT Emp_id, Emp_name, Pos, email, phone, hire_date, is_full_time, is_manager FROM Employee")
    employees = cur.fetchall()
    cur.close()
    return render_template('view_employees.html', employees=employees)

@app.route('/edit_employee/<int:emp_id>', methods=['GET', 'POST'])
def edit_employee(emp_id):
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager access required', 'danger')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor(DictCursor)
    cur.execute("SELECT * FROM Employee WHERE Emp_id = %s", (emp_id,))
    employee = cur.fetchone()

    if request.method == 'POST':
        name = request.form['name']
        position = request.form['position']
        phone = request.form.get('phone')
        is_full_time = 'is_full_time' in request.form
        is_manager = 'is_manager' in request.form

        cur.execute("""
            UPDATE Employee SET Emp_name = %s, Pos = %s, phone = %s, is_full_time = %s, is_manager = %s
            WHERE Emp_id = %s
        """, (name, position, phone, is_full_time, is_manager, emp_id))
        mysql.connection.commit()

        # Handle full-time/part-time table updates
        if is_full_time:
            # If changed to full-time, ensure it's in Full_time table
            cur.execute("INSERT IGNORE INTO Full_time (Emp_id, Salary) VALUES (%s, 0.00)", (emp_id,))
            cur.execute("DELETE FROM Part_time WHERE Emp_id = %s", (emp_id,))
        else:
            # If changed to part-time, ensure it's in Part_time table
            cur.execute("INSERT IGNORE INTO Part_time (Emp_id, Work_hours, Hour_price) VALUES (%s, 0, 0.00)", (emp_id,))
            cur.execute("DELETE FROM Full_time WHERE Emp_id = %s", (emp_id,))
        
        mysql.connection.commit()
        cur.close()
        flash('Employee updated successfully!', 'success')
        return redirect(url_for('view_employees'))
    
    cur.close()
    if employee:
        return render_template('edit_employee.html', employee=employee)
    else:
        flash('Employee not found!', 'danger')
        return redirect(url_for('view_employees'))


@app.route('/delete_employee/<int:emp_id>', methods=['POST'])
def delete_employee(emp_id):
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager access required', 'danger')
        return redirect(url_for('login'))
    
    if emp_id == session['employee_id']:
        flash("You cannot delete your own account!", 'danger')
        return redirect(url_for('view_employees'))

    cur = mysql.connection.cursor()
    try:
        # Delete from Full_time or Part_time first if exists
        cur.execute("DELETE FROM Full_time WHERE Emp_id = %s", (emp_id,))
        cur.execute("DELETE FROM Part_time WHERE Emp_id = %s", (emp_id,))
        
        # Delete from Manager table if this employee was a manager or managed someone
        cur.execute("DELETE FROM Manager WHERE manager_id = %s OR employee_id = %s", (emp_id, emp_id))

        # Update shipments where this employee is recorded as 'received by'
        cur.execute("UPDATE Shipments SET employee_id = NULL WHERE employee_id = %s", (emp_id,))

        # Update orders where this employee is recorded (if applicable, e.g., employee_id in Order table)
        cur.execute("UPDATE `Order` SET employee_id = NULL WHERE employee_id = %s", (emp_id,)) # Set to NULL or reassign

        # Finally, delete from Employee table
        cur.execute("DELETE FROM Employee WHERE Emp_id = %s", (emp_id,))
        mysql.connection.commit()
        flash('Employee deleted successfully!', 'success')
    except MySQLdb.Error as e:
        flash(f"Error deleting employee: {e}", 'danger')
        mysql.connection.rollback()
    finally:
        cur.close()
    return redirect(url_for('view_employees'))


@app.route('/manager/add_employee', methods=['GET', 'POST'])
def add_employee():
    if 'employee_id' not in session or not session.get('is_manager'):
        flash('Manager access required', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        position = request.form['position']
        phone = request.form['phone']
        password = request.form['password']
        is_manager = 'is_manager' in request.form
        
        hashed_password = generate_password_hash(password)

        cur = mysql.connection.cursor()
        try:
            # Check if email already exists
            cur.execute("SELECT COUNT(*) FROM Employee WHERE email = %s", (email,))
            if cur.fetchone()[0] > 0:
                flash('Employee with this email already exists.', 'danger')
                return render_template('add_employee.html')

            cur.execute(
                "INSERT INTO Employee (Emp_name, Pos, email, phone, hire_date, is_manager, password) VALUES (%s, %s, %s, %s, CURDATE(), %s, %s)",
                (name, position, email, phone, is_manager, hashed_password)
            )
            mysql.connection.commit()
            flash('Employee added successfully!', 'success')
            return redirect(url_for('view_employees'))
        except MySQLdb.Error as e:
            flash(f"Error adding employee: {e}", 'danger')
            mysql.connection.rollback()
        finally:
            cur.close()

    return render_template('add_employee.html')
# --- NEW ROUTE FOR SHOP PAGE ---
@app.route('/add_to_cart/<int:cake_id>', methods=['POST'])
def add_to_cart(cake_id):

    
   
    if 'cart' not in session:
        session['cart'] = {} # A dictionary to store {cake_id: quantity}

    quantity = request.form.get('quantity', 1, type=int) # Get quantity from form, default to 1

    cur = None
    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT cake_id, name, price, stock, image_url FROM Cake WHERE cake_id = %s AND available = TRUE", (cake_id,))
        cake = cur.fetchone()

        if cake:
            if quantity > cake['stock']:
                flash(f'Sorry, only {cake["stock"]} of {cake["name"]} are available.', 'warning')
            else:
                # Add cake to cart in session
                # If cake already in cart, update quantity
                session['cart'][str(cake_id)] = session['cart'].get(str(cake_id), 0) + quantity
                session.modified = True # Tell Flask the session has been modified

                flash(f'{quantity} x {cake["name"]} added to cart!', 'success')
        else:
            flash('Cake not found or not available.', 'danger')

    except Exception as e:
        flash(f'Error adding item to cart: {e}', 'danger')
        print(f"Error in add_to_cart: {e}")
    finally:
        if cur:
            cur.close()

    # Redirect back to the shop page or a dedicated cart page
    return redirect(url_for('shop')) # or redirect(url_for('view_cart')) if you create one


@app.route('/view_cart')
def view_cart():
    cart_items = []
    total_price = 0
    
    if 'cart' in session and session['cart']:
        cake_ids = list(session['cart'].keys())
        if cake_ids:
            cur = None
            try:
                cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
                # Fetch details for all cakes in the cart
                placeholders = ','.join(['%s'] * len(cake_ids))
                cur.execute(f"SELECT cake_id, name, price, image_url FROM Cake WHERE cake_id IN ({placeholders})", tuple(cake_ids))
                cakes_details = {cake['cake_id']: cake for cake in cur.fetchall()}

                for cake_id_str, quantity in session['cart'].items():
                    cake_id = int(cake_id_str)
                    if cake_id in cakes_details:
                        cake = cakes_details[cake_id]
                        item_total = cake['price'] * quantity
                        cart_items.append({
                            'cake_id': cake['cake_id'],
                            'name': cake['name'],
                            'price': cake['price'],
                            'image_url': cake['image_url'],
                            'quantity': quantity,
                            'total': item_total
                        })
                        total_price += item_total
            except Exception as e:
                flash(f'Error loading cart details: {e}', 'danger')
                print(f"Error in view_cart: {e}")
            finally:
                if cur:
                    cur.close()

    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

@app.route('/shop')
def shop():
    cakes = []
    selected_category = request.args.get('category', 'all').lower()
    cur = None

    try:
       
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor) 

        if selected_category == 'all':
            cur.execute("SELECT cake_id, name, description, price, stock, category, image_url, popularity, available FROM Cake WHERE available = TRUE ORDER BY popularity DESC")
        else:
            cur.execute("SELECT cake_id, name, description, price, stock, category, image_url, popularity, available FROM Cake WHERE category = %s AND available = TRUE ORDER BY popularity DESC", (selected_category,))
        
        cakes = cur.fetchall() 

    except Exception as e:
        flash(f"An error occurred while fetching cakes: {e}", 'danger')
        print(f"Database error in shop(): {e}") 
    finally:
        if cur:
            cur.close()

    return render_template('shop.html', cakes=cakes, selected_category=selected_category)
# --- Employee Schedule ---
@app.route('/my_schedule')
def my_schedule():
    if 'employee_id' not in session:
        flash('Employee login required', 'danger')
        return redirect(url_for('login'))

    emp_id = session['employee_id']
    cur = mysql.connection.cursor(DictCursor)
    
    cur.execute("SELECT Emp_name, schedule, is_full_time FROM Employee WHERE Emp_id = %s", (emp_id,))
    employee_schedule_info = cur.fetchone()
    
    cur.close()

    if employee_schedule_info:
        return render_template('schedule.html', schedule=employee_schedule_info)
    else:
        flash('Could not retrieve schedule information.', 'warning')
        return redirect(url_for('dashboard'))

@app.route('/confirm_order', methods=['GET', 'POST'])
def confirm_order():
    # Ensure cart is not empty
    if 'cart' not in session or not session['cart']:
        flash('Your cart is empty. Please add items before confirming your order.', 'warning')
        return redirect(url_for('shop'))

    cart_items = []
    total_price = 0
    cur = None
    
    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cake_ids_str = list(session['cart'].keys())
        cake_ids = [int(id_str) for id_str in cake_ids_str]

        if cake_ids:
            placeholders = ','.join(['%s'] * len(cake_ids))
            cur.execute(f"SELECT cake_id, name, price, image_url, stock FROM Cake WHERE cake_id IN ({placeholders})", tuple(cake_ids))
            cakes_details_list = cur.fetchall()
            cakes_details = {cake['cake_id']: cake for cake in cakes_details_list}

            # Check stock availability for each item in the cart
            for cake_id_str, quantity in session['cart'].items():
                cake_id = int(cake_id_str)
                if cake_id in cakes_details:
                    cake = cakes_details[cake_id]
                    
                    # IMPORTANT: Check stock before confirming
                    if quantity > cake['stock']:
                        flash(f'Insufficient stock for {cake["name"]}. Available: {cake["stock"]}, Your quantity: {quantity}', 'danger')
                        return redirect(url_for('view_cart')) # Redirect back to cart if stock is an issue

                    item_total = cake['price'] * quantity
                    cart_items.append({
                        'cake_id': cake['cake_id'],
                        'name': cake['name'],
                        'price': cake['price'],
                        'image_url': cake['image_url'],
                        'quantity': quantity,
                        'total': item_total
                    })
                    total_price += item_total
                else:
                    # If a cake in cart is no longer in DB (e.g., deleted), remove from cart
                    del session['cart'][cake_id_str]
                    session.modified = True
                    flash(f"One or more items in your cart are no longer available and have been removed.", 'warning')
                    return redirect(url_for('view_cart'))

    except Exception as e:
        flash(f'Error preparing order confirmation: {e}', 'danger')
        print(f"Error in confirm_order (GET): {e}")
        return redirect(url_for('view_cart')) # Redirect to cart on error
    finally:
        if cur:
            cur.close()

    # If GET request, just display the confirmation page
    if request.method == 'GET':
        return render_template('confirm_order.html', cart_items=cart_items, total_price=total_price)

    # If POST request (user clicked "Place Order" on confirm_order.html)
    elif request.method == 'POST':



        try:
            cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            
            # Start a transaction for atomicity (optional but good practice for orders)
            mysql.connection.autocommit(False) 

            # 1. Create a new order entry
            customer_id = session.get('user_id') # Assuming you store customer_id in session
            if not customer_id:
                flash('You must be logged in to place an order.', 'danger')
                return redirect(url_for('login'))
            
            # Basic order insertion (you might have more fields like address, payment_method, etc.)
            cur.execute("INSERT INTO Orders (customer_id, order_date, total_amount, status) VALUES (%s, NOW(), %s, %s)",
                        (customer_id, total_price, 'Pending'))
            order_id = cur.lastrowid # Get the ID of the newly created order

            # 2. Add items to Order_Items table and update cake stock
            for item in cart_items: # Use the cart_items prepared earlier
                cur.execute("INSERT INTO Order_Item (order_id, cake_id, quantity, price_at_purchase) VALUES (%s, %s, %s, %s)",
                            (order_id, item['cake_id'], item['quantity'], item['price']))
                
                # Decrement stock
                cur.execute("UPDATE Cake SET stock = stock - %s WHERE cake_id = %s",
                            (item['quantity'], item['cake_id']))
            
            mysql.connection.commit() # Commit the transaction
            session.pop('cart', None) # 3. Clear the cart after successful order
            session.modified = True # Important to mark session as modified

            flash('Your order has been placed successfully!', 'success')
            return redirect(url_for('order_success', order_id=order_id)) # Redirect to a success page

        except Exception as e:
            mysql.connection.rollback() # Rollback transaction on error
            flash(f'Failed to place order: {e}', 'danger')
            print(f"Error placing order: {e}")
            return redirect(url_for('view_cart')) # Redirect back to cart or confirmation

    return render_template('confirm_order.html', cart_items=cart_items, total_price=total_price)


# You'll also need an 'order_success' route
@app.route('/order_success/<int:order_id>')
def order_success(order_id):
    # This page just confirms the order was placed.
    # You might fetch order details here to display.
    return render_template('order_success.html', order_id=order_id)
if __name__ == '__main__':
    app.run(debug=True)