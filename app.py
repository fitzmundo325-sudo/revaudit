import os
import json
import calendar
from functools import wraps
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, Response, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

db = SQLAlchemy()

UNITS = ['Sir Q Expense', 'Management', 'Cluster1', 'Cluster2', 'Cluster3',
         'Cluster4', 'Cluster5', 'Cluster6', 'Internal Audit']

ACCOUNT_TITLES = ['Transportation & Travel', 'Meal Allowance',
                   'Employees Housing Allowance', 'Water', 'Miscellaneous']

# Short display columns for the dashboard, matching the original sheet's layout
DASHBOARD_COLS = [
    ('Transportation & Travel', 'Transportation & Travel'),
    ('Meal Allowance', 'Meal Allowance'),
    ('Employees Housing Allowance', 'Housing Allowance'),
    ('Water', 'Water'),
    ('Miscellaneous', 'Miscellaneous'),
]


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    unit = db.Column(db.String(64), nullable=False, index=True)
    payee = db.Column(db.String(255))
    branch = db.Column(db.String(128))
    trxn_date = db.Column(db.Date, index=True)
    particulars = db.Column(db.Text)
    ref_no = db.Column(db.String(128))
    account_title = db.Column(db.String(64), index=True)
    tin = db.Column(db.String(64))
    address = db.Column(db.String(255))
    amount = db.Column(db.Float, nullable=False, default=0)
    prepared_by = db.Column(db.String(128), default='Jenny Rose Ando')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'unit': self.unit,
            'payee': self.payee,
            'branch': self.branch,
            'trxn_date': self.trxn_date.isoformat() if self.trxn_date else None,
            'particulars': self.particulars,
            'ref_no': self.ref_no,
            'account_title': self.account_title,
            'tin': self.tin,
            'address': self.address,
            'amount': self.amount,
            'prepared_by': self.prepared_by,
        }


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'revolving-fund-dev-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'revfund.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        seed_if_empty()
        seed_user_if_empty()

    register_routes(app)
    return app


def seed_user_if_empty():
    if User.query.first():
        return
    db.session.add(User(username='Jenny', password_hash=generate_password_hash('jenny_081226')))
    db.session.commit()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user'):
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def seed_if_empty():
    if Expense.query.first() is not None:
        return
    seed_path = os.path.join(BASE_DIR, 'seed_data.json')
    if not os.path.exists(seed_path):
        return
    with open(seed_path) as f:
        rows = json.load(f)
    for r in rows:
        db.session.add(Expense(
            unit=r['unit'],
            payee=r['payee'],
            branch=r['branch'],
            trxn_date=parse_date(r['trxn_date']),
            particulars=r['particulars'],
            ref_no=r['ref_no'],
            account_title=r['account_title'],
            tin=r['tin'],
            address=r['address'],
            amount=r['amount'],
        ))
    db.session.commit()


def month_bounds(year, month):
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    return first, last


def build_dashboard(year, month):
    first, last = month_bounds(year, month)

    month_expenses = Expense.query.filter(Expense.trxn_date >= first, Expense.trxn_date <= last).all()

    # Per-unit x account-title matrix for the selected month
    matrix = {u: {a: 0.0 for a, _ in DASHBOARD_COLS} for u in UNITS}
    for e in month_expenses:
        if e.unit in matrix and e.account_title in matrix[e.unit]:
            matrix[e.unit][e.account_title] += e.amount

    unit_rows = []
    grand_totals = {a: 0.0 for a, _ in DASHBOARD_COLS}
    grand_total_all = 0.0
    for u in UNITS:
        row_total = sum(matrix[u].values())
        unit_rows.append({'unit': u, 'amounts': matrix[u], 'total': row_total})
        for a, _ in DASHBOARD_COLS:
            grand_totals[a] += matrix[u][a]
        grand_total_all += row_total

    for row in unit_rows:
        row['pct'] = (row['total'] / grand_total_all * 100) if grand_total_all else 0

    key_metrics = {
        'total_expenses': grand_total_all,
        'num_transactions': len(month_expenses),
        'transportation': grand_totals.get('Transportation & Travel', 0),
        'meal': grand_totals.get('Meal Allowance', 0),
        'housing': grand_totals.get('Employees Housing Allowance', 0),
        'water': grand_totals.get('Water', 0),
        'misc': grand_totals.get('Miscellaneous', 0),
    }

    # Full-year monthly summary (Jan-Dec of the selected year)
    monthly_rows = []
    year_grand = {a: 0.0 for a, _ in DASHBOARD_COLS}
    year_grand_total = 0.0
    for m in range(1, 13):
        mfirst, mlast = month_bounds(year, m)
        rows = Expense.query.filter(Expense.trxn_date >= mfirst, Expense.trxn_date <= mlast).all()
        totals = {a: 0.0 for a, _ in DASHBOARD_COLS}
        for e in rows:
            if e.account_title in totals:
                totals[e.account_title] += e.amount
        total = sum(totals.values())
        monthly_rows.append({
            'label': calendar.month_name[m] + f' {year}',
            'month': m,
            'amounts': totals,
            'total': total,
        })
        for a, _ in DASHBOARD_COLS:
            year_grand[a] += totals[a]
        year_grand_total += total

    for row in monthly_rows:
        row['pct'] = (row['total'] / year_grand_total * 100) if year_grand_total else 0

    return {
        'year': year,
        'month': month,
        'month_label': calendar.month_name[month],
        'key_metrics': key_metrics,
        'unit_rows': unit_rows,
        'grand_totals': grand_totals,
        'grand_total_all': grand_total_all,
        'monthly_rows': monthly_rows,
        'year_grand': year_grand,
        'year_grand_total': year_grand_total,
    }


def register_routes(app):

    @app.context_processor
    def inject_current_user():
        return {'current_user': session.get('user')}

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if session.get('user'):
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                session['user'] = user.username
                flash(f'Welcome back, {user.username}.', 'success')
                return redirect(url_for('dashboard'))
            flash('Invalid username or password.', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.pop('user', None)
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))

    @app.route('/')
    def index():
        return redirect(url_for('dashboard'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        today = date.today()
        year = request.args.get('year', type=int, default=today.year)
        month = request.args.get('month', type=int, default=today.month)
        data = build_dashboard(year, month)
        return render_template('dashboard.html', cols=DASHBOARD_COLS, units=UNITS, **data)

    @app.route('/unit/<unit_name>')
    @login_required
    def unit_ledger(unit_name):
        if unit_name not in UNITS:
            flash('Unknown unit', 'danger')
            return redirect(url_for('dashboard'))
        q = Expense.query.filter_by(unit=unit_name)
        account_filter = request.args.get('account_title')
        if account_filter:
            q = q.filter_by(account_title=account_filter)
        entries = q.order_by(Expense.trxn_date.asc().nullslast(), Expense.id.asc()).all()
        total = sum(e.amount for e in entries)
        return render_template('ledger.html', unit=unit_name, units=UNITS, entries=entries,
                                total=total, account_titles=ACCOUNT_TITLES,
                                account_filter=account_filter)

    @app.route('/unit/<unit_name>/add', methods=['POST'])
    @login_required
    def add_entry(unit_name):
        if unit_name not in UNITS:
            return jsonify({'error': 'Unknown unit'}), 400
        form = request.form
        try:
            amount = float(form.get('amount', 0) or 0)
        except ValueError:
            amount = 0
        entry = Expense(
            unit=unit_name,
            payee=form.get('payee', '').strip(),
            branch=form.get('branch', '').strip() or None,
            trxn_date=parse_date(form.get('trxn_date')),
            particulars=form.get('particulars', '').strip() or None,
            ref_no=form.get('ref_no', '').strip() or None,
            account_title=form.get('account_title') or None,
            tin=form.get('tin', '').strip() or None,
            address=form.get('address', '').strip() or None,
            amount=amount,
            prepared_by=form.get('prepared_by', 'Jenny Rose Ando').strip() or 'Jenny Rose Ando',
        )
        db.session.add(entry)
        db.session.commit()
        flash('Expense entry added.', 'success')
        return redirect(url_for('unit_ledger', unit_name=unit_name))

    @app.route('/entry/<int:entry_id>/edit', methods=['POST'])
    @login_required
    def edit_entry(entry_id):
        entry = Expense.query.get_or_404(entry_id)
        form = request.form
        try:
            amount = float(form.get('amount', entry.amount) or 0)
        except ValueError:
            amount = entry.amount
        entry.payee = form.get('payee', entry.payee).strip()
        entry.branch = form.get('branch', entry.branch)
        entry.trxn_date = parse_date(form.get('trxn_date')) or entry.trxn_date
        entry.particulars = form.get('particulars', entry.particulars)
        entry.ref_no = form.get('ref_no', entry.ref_no)
        entry.account_title = form.get('account_title', entry.account_title)
        entry.tin = form.get('tin', entry.tin)
        entry.address = form.get('address', entry.address)
        entry.amount = amount
        entry.prepared_by = form.get('prepared_by', entry.prepared_by).strip() or 'Jenny Rose Ando'
        db.session.commit()
        flash('Expense entry updated.', 'success')
        return redirect(url_for('unit_ledger', unit_name=entry.unit))

    @app.route('/entry/<int:entry_id>/delete', methods=['POST'])
    @login_required
    def delete_entry(entry_id):
        entry = Expense.query.get_or_404(entry_id)
        unit_name = entry.unit
        db.session.delete(entry)
        db.session.commit()
        flash('Expense entry deleted.', 'info')
        return redirect(url_for('unit_ledger', unit_name=unit_name))

    @app.route('/api/expenses')
    @login_required
    def api_expenses():
        unit = request.args.get('unit')
        q = Expense.query
        if unit:
            q = q.filter_by(unit=unit)
        return jsonify([e.to_dict() for e in q.all()])

    @app.route('/export/<unit_name>.csv')
    @login_required
    def export_csv(unit_name):
        if unit_name not in UNITS:
            return 'Unknown unit', 404
        entries = Expense.query.filter_by(unit=unit_name).order_by(Expense.trxn_date.asc()).all()
        lines = ['Payee,Branch,Transaction Date,Particulars,Ref#,Account Title,TIN,Address,Amount']
        for e in entries:
            row = [e.payee, e.branch, e.trxn_date.isoformat() if e.trxn_date else '',
                   e.particulars, e.ref_no, e.account_title, e.tin, e.address, str(e.amount)]
            row = ['' if v is None else str(v).replace(',', ';').replace('\n', ' ') for v in row]
            lines.append(','.join(row))
        csv_data = '\n'.join(lines)
        return Response(csv_data, mimetype='text/csv',
                         headers={'Content-Disposition': f'attachment; filename={unit_name}_expenses.csv'})


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
