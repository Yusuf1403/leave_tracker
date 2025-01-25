import csv
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
from datetime import datetime, timedelta
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = '45273cd5009863c6b7008e37ab88357a'

USERS_CSV = r'C:\Users\NTS-YusufShaikh\Desktop\Leave_Calendar_New\data\users.csv'
LEAVES_CSV = 'data/leaves.csv'
LEAVE_BALANCE_CSV = 'data/leave_balance.csv'

user_data = []
with open('data/users.csv', 'r') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        user_data.append(row)

os.makedirs('data', exist_ok=True)

if not os.path.exists(USERS_CSV):
    pd.DataFrame({
        'username': ['admin', 'manager1', 'emp1', 'emp2'],
        'password': ['admin123', 'mgr123', 'emp123', 'emp456'],
        'role': ['admin', 'manager', 'employee', 'employee'],
        'team': ['admin', 'team1', 'team1', 'team1']
    }).to_csv(USERS_CSV, index=False)

if not os.path.exists(LEAVES_CSV):
    pd.DataFrame({
        'id': [], 'username': [], 'leave_type': [], 'from': [], 'to': [],
        'reason': [], 'status': [], 'team': [], 'applied_date': []
    }).to_csv(LEAVES_CSV, index=False)

if not os.path.exists(LEAVE_BALANCE_CSV):
    pd.DataFrame({
        'username': ['emp1', 'emp2'],
        'sick_leave': [12, 12], 'casual_leave': [12, 12], 'earned_leave': [15, 15]
    }).to_csv(LEAVE_BALANCE_CSV, index=False)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] not in ['manager', 'admin']:
            flash('Unauthorized access', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users_df = pd.read_csv(USERS_CSV)
        user = users_df[users_df['username'] == username]
        if not user.empty and user.iloc[0]['password'] == password:
            session['username'] = username
            session['role'] = user.iloc[0]['role']
            session['team'] = user.iloc[0]['team']
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    username = session['username']
    balance_df = pd.read_csv(LEAVE_BALANCE_CSV)
    user_balance = balance_df[balance_df['username'] == username].iloc[0].to_dict() if not balance_df[balance_df['username'] == username].empty else {}
    leaves_df = pd.read_csv(LEAVES_CSV)
    user_leaves = leaves_df[leaves_df['username'] == username].to_dict('records')
    return render_template('dashboard.html', leaves=user_leaves, balance=user_balance, is_manager=(session['role'] in ['manager', 'admin']))


@app.route('/associates_view')
@login_required
@manager_required
def associates_view():
    # Get the current manager's team
    team = session['team']
    
    # Read CSV files
    users_df = pd.read_csv(USERS_CSV)
    leaves_df = pd.read_csv(LEAVES_CSV)
    leave_balance_df = pd.read_csv(LEAVE_BALANCE_CSV)
    
    # Filter associates in the manager's team
    if session['role'] == 'admin':
        team_users = users_df[users_df['role'] == 'employee']
    else:
        team_users = users_df[(users_df['team'] == team) & (users_df['role'] == 'employee')]
    
    # Get today's date
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Prepare associates data with more comprehensive information
    associates_data = []
    for _, user in team_users.iterrows():
        # Get leave balance for the user
        user_balance = leave_balance_df[leave_balance_df['username'] == user['username']]
        
        # Check current leaves
        current_leave = leaves_df[
            (leaves_df['username'] == user['username']) & 
            (leaves_df['from'] <= today) & 
            (leaves_df['to'] >= today) & 
            (leaves_df['status'] == 'Approved')
        ]
        
        # Get all leave history for the user
        user_leave_history = leaves_df[leaves_df['username'] == user['username']].to_dict('records')
        
        # Prepare associate details
        associate_info = {
            'username': user['username'],
            'is_on_leave': not current_leave.empty,
            'current_leave': current_leave.to_dict('records')[0] if not current_leave.empty else None,
            'leave_balance': user_balance.iloc[0].to_dict() if not user_balance.empty else {
                'sick_leave': 0,
                'casual_leave': 0,
                'earned_leave': 0
            },
            'leave_history': user_leave_history
        }
        
        # Ensure duration is set for current leave
        if associate_info['current_leave']:
            associate_info['current_leave']['duration'] = associate_info['current_leave'].get('duration', 'Full Day')
        
        associates_data.append(associate_info)
    
    return render_template('associates_view.html', associates=associates_data)


@app.route('/apply_leave', methods=['GET', 'POST'])
@login_required
def apply_leave():
    username = session['username']
    balance_df = pd.read_csv(LEAVE_BALANCE_CSV)
    
    # Handle case where user might not exist in leave balance
    user_balance = balance_df[balance_df['username'] == username]
    if user_balance.empty:
        # Create default balance if not exists
        default_balance = {
            'username': username, 
            'sick_leave': 12, 
            'casual_leave': 12, 
            'earned_leave': 15
        }
        balance_df = balance_df.append(default_balance, ignore_index=True)
        balance_df.to_csv(LEAVE_BALANCE_CSV, index=False)
        user_balance = pd.DataFrame([default_balance])
    
    user_balance = user_balance.iloc[0].to_dict()
    
    if request.method == 'POST':
        leave_type = request.form['leave_type']
        start_date = request.form['from_date']
        end_date = request.form['to_date']
        leave_duration = request.form.get('leave_duration', 'Full Day')
        reason = request.form['reason']
        attachment = request.files.get('attachment')
        
        # Convert dates to datetime objects
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        today = datetime.now()
        
        # Validate date range
        if start > end:
            flash('Start date must be before or equal to end date', 'error')
            return redirect(url_for('apply_leave'))

        def count_working_days(start, end, leave_duration):
            total_days = 0
            current = start
            while current <= end:
                # Skip weekends
                if current.weekday() < 5:
                    total_days += 1
                current += timedelta(days=1)
            
            # Adjust for half-day
            if leave_duration == 'Half Day':
                total_days = 0.5
            
            # Ensure at least 1 day is counted when start and end dates are different
            return max(total_days, 1 if start != end else 1)
        
        # Specific validation for different leave types
        if leave_type != 'Sick Leave':
            # Non-sick leaves for future dates must be applied 7 days in advance
            if start.date() > today.date():
                min_apply_date = today + timedelta(days=7)
                if start.date() < min_apply_date.date():
                    flash(f'{leave_type} must be applied at least 7 days in advance', 'error')
                    return redirect(url_for('apply_leave'))
            
            # Non-sick leaves cannot be applied for past dates
            if start.date() < today.date():
                flash(f'{leave_type} cannot be applied for past dates', 'error')
                return redirect(url_for('apply_leave'))
        else:
            # Sick leave can be applied for past dates, but requires attachment
            if (attachment is None or attachment.filename == '') and leave_type == 'Sick Leave':
                flash('Attachment is required for Sick Leave', 'error')
                return redirect(url_for('apply_leave'))
        
        # Calculate total days, ensuring at least 1 day for single-day leaves
        total_days = max(count_working_days(start, end, leave_duration), 1)
        
        # Check leave balance
        leave_type_column = leave_type.lower().replace(' ', '_')
        
        # Deduct correct amount from leave balance
        if leave_type_column in user_balance:
            # Correctly deduct leave balance
            if leave_duration == 'Half Day':
                if user_balance.get(leave_type_column, 0) >= 0.5:
                    balance_df.loc[balance_df['username'] == username, leave_type_column] -= 0.5
                else:
                    flash(f'Insufficient {leave_type} balance', 'error')
                    return redirect(url_for('apply_leave'))
            else:
                if user_balance.get(leave_type_column, 0) >= total_days:
                    balance_df.loc[balance_df['username'] == username, leave_type_column] -= total_days
                else:
                    flash(f'Insufficient {leave_type} balance', 'error')
                    return redirect(url_for('apply_leave'))
        
        balance_df.to_csv(LEAVE_BALANCE_CSV, index=False)
        
        # Save attachment for sick leave
        attachment_path = None
        if attachment and leave_type == 'Sick Leave':
            os.makedirs('uploads', exist_ok=True)
            filename = f"{username}_{start_date}_sick_leave{os.path.splitext(attachment.filename)[1]}"
            attachment_path = os.path.join('uploads', filename)
            attachment.save(attachment_path)
        
        # Save leave application
        leaves_df = pd.read_csv(LEAVES_CSV)
        new_leave = pd.DataFrame([{
            'id': len(leaves_df) + 1, 
            'username': username, 
            'leave_type': leave_type,
            'from': start_date, 
            'to': end_date, 
            'reason': reason,
            'status': 'Pending', 
            'team': session['team'], 
            'applied_date': today.strftime('%Y-%m-%d'),
            'duration': leave_duration,
            'total_days': total_days,
            'attachment': attachment_path or ''
        }])
        leaves_df = pd.concat([leaves_df, new_leave], ignore_index=True)
        leaves_df.to_csv(LEAVES_CSV, index=False)
        
        flash('Leave application submitted successfully', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('apply_leave.html', balance=user_balance)






@app.route('/calendar_view')
@login_required
def calendar_view():
    leaves_df = pd.read_csv(LEAVES_CSV)
    
    # Process leaves for the entire year of 2025
    leaves_data = {}
    
    # Filter leaves for 2025
    year_leaves = leaves_df[
        (leaves_df['from'].str.startswith('2025')) | 
        (leaves_df['to'].str.startswith('2025'))
    ]
    
    # Group leaves by date
    for _, leave in year_leaves.iterrows():
        start_date = datetime.strptime(leave['from'], '%Y-%m-%d')
        end_date = datetime.strptime(leave['to'], '%Y-%m-%d')
        
        current = start_date
        while current <= end_date:
            date_str = current.strftime('%Y-%m-%d')
            
            if date_str not in leaves_data:
                leaves_data[date_str] = []
            
            leaves_data[date_str].append({
                'username': leave['username'],
                'leave_type': leave['leave_type'],
                'status': leave['status']
            })
            
            current += timedelta(days=1)
    
    # Get team usernames for filter dropdown
    if session['role'] == 'admin':
        users_df = pd.read_csv(USERS_CSV)
        usernames = users_df[users_df['role'] == 'employee']['username'].tolist()
    else:
        users_df = pd.read_csv(USERS_CSV)
        usernames = users_df[
            (users_df['team'] == session['team']) & 
            (users_df['role'] == 'employee')
        ]['username'].tolist()
    
    return render_template('calendar_view.html', 
                           leaves_data=leaves_data, 
                           usernames=usernames)
    
    

@app.route('/manager_view')
@login_required
@manager_required
def manager_view():
    team = session['team']
    users_df = pd.read_csv(USERS_CSV)
    leaves_df = pd.read_csv(LEAVES_CSV)
    leave_balance_df = pd.read_csv(LEAVE_BALANCE_CSV)
    
    # Filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    selected_username = request.args.get('username')
    
    # Get today's date
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Filter leaves for the team
    if session['role'] == 'admin':
        team_leaves = leaves_df
        team_users = users_df
    else:
        team_leaves = leaves_df[leaves_df['team'] == team]
        team_users = users_df[users_df['team'] == team]
    
    # Apply username filter
    if selected_username:
        team_leaves = team_leaves[team_leaves['username'] == selected_username]
    
    # Apply date range filter
    if start_date and end_date:
        team_leaves = team_leaves[
            (team_leaves['from'] >= start_date) & 
            (team_leaves['to'] <= end_date)
        ]
    
    # Pending leaves with top 4 requests
    pending_leaves = team_leaves[team_leaves['status'] == 'Pending'].head(4)
    
    # Count of associates and leaves today
    total_associates = len(team_users)
    leaves_today = team_leaves[(team_leaves['from'] <= today) & (team_leaves['to'] >= today) & (team_leaves['status'] == 'Approved')]
    associates_on_leave = len(leaves_today['username'].unique())
    
    # Get unique usernames for filter dropdown
    team_usernames = team_users['username'].unique().tolist()
    
    return render_template('manager_view.html', 
                           leaves=pending_leaves.to_dict('records'), 
                           total_associates=total_associates, 
                           associates_on_leave=associates_on_leave,
                           team=team,
                           usernames=team_usernames)


@app.route('/update_leave_status/<int:leave_id>/<status>')
@login_required
@manager_required
def update_leave_status(leave_id, status):
    leaves_df = pd.read_csv(LEAVES_CSV)
    leaves_df.loc[leaves_df['id'] == leave_id, 'status'] = status
    if status == 'Approved':
        leave_type = leaves_df[leaves_df['id'] == leave_id].iloc[0]['leave_type'].lower().replace(' ', '_')
        username = leaves_df[leaves_df['id'] == leave_id].iloc[0]['username']
        balance_df = pd.read_csv(LEAVE_BALANCE_CSV)
        balance_df.loc[balance_df['username'] == username, leave_type] -= 1
        balance_df.to_csv(LEAVE_BALANCE_CSV, index=False)
    leaves_df.to_csv(LEAVES_CSV, index=False)
    flash(f'Leave {status.lower()}', 'success')
    return redirect(url_for('manager_view'))

@app.route('/profile')
@login_required
def profile():
    users_df = pd.read_csv(USERS_CSV)
    username = session['username']
    current_user = users_df[users_df['username'] == username]
    if not current_user.empty:
        user_info = current_user.iloc[0].to_dict()
        return render_template('profile.html', user_info=user_info)
    else:
        flash('User profile not found', 'error')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)