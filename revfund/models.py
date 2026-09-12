from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(100), nullable=False, default='Admin')
    # Separate access level for ledger data: 'Viewer' (read-only) or 'Editor'
    # (can add/edit/import/delete expense entries). Privileged roles always
    # behave as editors regardless of this value.
    access_level = db.Column(db.String(20), nullable=False, default='Viewer', server_default='Viewer')
    created_at = db.Column(db.DateTime, default=func.now())
    last_activity_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Roles that manage the system; their ledger access is always full.
    PRIVILEGED = {'Admin', 'Superadmin', 'Auditor'}

    @property
    def can_modify_data(self):
        return self.role in self.PRIVILEGED or self.access_level == 'Editor'

    @property
    def is_active(self):
        # Deactivated accounts are kept in the database (audit history) but
        # can never authenticate. Flask-Login consults this on every request.
        return not self.username.startswith('deactivated:')

    @is_active.setter
    def is_active(self, value):
        if not value and not self.username.startswith('deactivated:'):
            self.username = 'deactivated:' + self.username
        elif value and self.username.startswith('deactivated:'):
            self.username = self.username.split('deactivated:', 1)[1]


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    unit = db.Column(db.String(64), nullable=False, index=True)
    payee = db.Column(db.String(255))
    branch = db.Column(db.String(128))
    trxn_date = db.Column(db.Date, index=True)
    particulars = db.Column(db.Text)
    ref_no = db.Column(db.String(128))
    trxn_code = db.Column(db.String(128))
    account_title = db.Column(db.String(64), index=True)
    tin = db.Column(db.String(64))
    address = db.Column(db.String(255))
    amount = db.Column(db.Float, nullable=False, default=0)
    prepared_by = db.Column(db.String(128), default='Jenny Rose Ando')
    created_at = db.Column(db.DateTime, default=func.now())
    updated_at = db.Column(db.DateTime, default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'unit': self.unit,
            'payee': self.payee,
            'branch': self.branch,
            'trxn_date': self.trxn_date.isoformat() if self.trxn_date else None,
            'particulars': self.particulars,
            'ref_no': self.ref_no,
            'trxn_code': self.trxn_code,
            'account_title': self.account_title,
            'tin': self.tin,
            'address': self.address,
            'amount': self.amount,
            'prepared_by': self.prepared_by,
        }


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_time = db.Column(db.DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    actor_username = db.Column(db.String(100))
    action = db.Column(db.String(120), nullable=False, index=True)
    entity_type = db.Column(db.String(80), index=True)
    entity_id = db.Column(db.String(120))
    reason = db.Column(db.String(255))
    ip_address = db.Column(db.String(64))
    endpoint = db.Column(db.String(255))
    http_method = db.Column(db.String(10))
    details = db.Column(db.Text)
    previous_hash = db.Column(db.String(64))
    current_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)

    actor = db.relationship('User', foreign_keys=[actor_user_id])


class SystemSecret(db.Model):
    __tablename__ = 'system_secret'

    id = db.Column(db.Integer, primary_key=True)
    secret_value = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())


class MaintenanceMode(db.Model):
    __tablename__ = 'maintenance_mode'

    id = db.Column(db.Integer, primary_key=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=False)
    message = db.Column(db.String(500), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now())
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    updater = db.relationship('User', foreign_keys=[updated_by])