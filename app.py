from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configure upload folder
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
print(f"Upload folder path: {os.path.abspath(UPLOAD_FOLDER)}")

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['hostelshare']

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.name = user_data['name']
        self.hostel = user_data['hostel']

@login_manager.user_loader
def load_user(user_id):
    user_data = db.users.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        hostel = request.form.get('hostel')
        mobile = request.form.get('mobile')

        if db.users.find_one({'email': email}):
            flash('Email already registered')
            return redirect(url_for('register'))

        user = {
            'email': email,
            'password': generate_password_hash(password),
            'name': name,
            'hostel': hostel,
            'mobile': mobile,
            'listed_items': [],
            'requests': []
        }
        db.users.insert_one(user)
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_data = db.users.find_one({'email': email})

        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_items = list(db.items.find({'owner_id': current_user.id}))
    # Convert ObjectId to string for each item
    for item in user_items:
        item['_id'] = str(item['_id'])
    user_requests = list(db.requests.find({'$or': [
        {'requester_id': current_user.id},
        {'item_id': {'$in': [str(item['_id']) for item in user_items]}}
    ]}))
    return render_template('dashboard.html', items=user_items, requests=user_requests)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    try:
        # Get the absolute path to the upload folder
        upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
        print(f"Attempting to serve file: {filename}")
        print(f"Upload path: {upload_path}")
        print(f"Full file path: {os.path.join(upload_path, filename)}")
        
        # Check if file exists
        if not os.path.exists(os.path.join(upload_path, filename)):
            print(f"File not found: {filename}")
            return "Image not found", 404
            
        return send_from_directory(upload_path, filename)
    except Exception as e:
        print(f"Error serving file {filename}: {str(e)}")
        return "Error serving image", 500

@app.route('/items/new', methods=['GET', 'POST'])
@login_required
def new_item():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        item_type = request.form.get('type')
        cost = request.form.get('cost')
        duration = request.form.get('duration')
        
        # Handle image upload
        image_url = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to filename to prevent duplicates
                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filename)
                print(f"Saving image to: {upload_path}")
                try:
                    file.save(upload_path)
                    if os.path.exists(upload_path):
                        print(f"Image saved successfully at: {upload_path}")
                        image_url = filename
                    else:
                        print(f"Failed to save image: {upload_path}")
                except Exception as e:
                    print(f"Error saving image: {str(e)}")
                    flash('Error saving image. Please try again.')
                    return redirect(url_for('new_item'))

        item = {
            'title': title,
            'description': description,
            'owner_id': current_user.id,
            'status': 'available',
            'type': item_type,
            'cost': cost,
            'duration': duration,
            'image_url': image_url,
            'created_at': datetime.utcnow()
        }
        db.items.insert_one(item)
        flash('Item listed successfully!')
        return redirect(url_for('dashboard'))
    return render_template('new_item.html')

@app.route('/items')
@login_required
def browse_items():
    items = list(db.items.find({'owner_id': {'$ne': current_user.id}}))
    return render_template('browse_items.html', items=items)

@app.route('/items/<item_id>')
@login_required
def item_details(item_id):
    item = db.items.find_one({'_id': ObjectId(item_id)})
    if not item:
        flash('Item not found')
        return redirect(url_for('browse_items'))
    
    # Get owner details
    owner = db.users.find_one({'_id': ObjectId(item['owner_id'])})
    if owner:
        item['owner_name'] = owner['name']
        item['owner_mobile'] = owner['mobile']
        item['owner_hostel'] = owner['hostel']
    
    return render_template('item_details.html', item=item)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 