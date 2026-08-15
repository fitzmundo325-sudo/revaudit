from flask import Blueprint, jsonify, request
from flask_login import login_required
from .models import Expense
from . import db

api_handles = Blueprint('api_handles', __name__)


@api_handles.route('/expenses')
@login_required
def api_expenses():
    unit = request.args.get('unit')
    q = Expense.query
    if unit:
        q = q.filter_by(unit=unit)
    return jsonify([e.to_dict() for e in q.all()])


@api_handles.route('/units')
@login_required
def api_units():
    from .views import UNITS
    return jsonify(UNITS)


@api_handles.route('/accounts')
@login_required
def api_accounts():
    from .views import ACCOUNT_TITLES
    return jsonify(ACCOUNT_TITLES)


@api_handles.route('/stats')
@login_required
def api_stats():
    total = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    count = db.session.query(db.func.count(Expense.id)).scalar() or 0
    return jsonify({'total_expenses': total, 'num_transactions': count})