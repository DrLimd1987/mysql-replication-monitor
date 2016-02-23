import mysql.connector
import datetime
import os
import time


class ReplicationChecker(object):
    def __init__(self, user, password, host='local', port=3306):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.notifiers = []
        self.messages = []

    def add_notifier(self, notifier):
        self.notifiers.append(notifier)

    def check(self):
        try:
            cnx = mysql.connector.connect(
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )

            cursor = cnx.cursor()
            query = 'SHOW SLAVE STATUS;'

            cursor.execute(query)
            replication_status_row = cursor.fetchall()[0]
            last_error_no = replication_status_row[18]
            last_error = replication_status_row[19]
            seconds_behind_master = replication_status_row[32]
            slave_sql_running_state = replication_status_row[44]

            if last_error_no != 0:
                self.raise_replication_error(last_error,
                                             slave_sql_running_state)
            elif seconds_behind_master > 300:
                self.track_lag(slave_sql_running_state)
            else:
                self.confirm_normality()

        except Exception as error:
            self.raise_exception(error)

        if self.messages:
            self.trigger_notifications()

    def raise_replication_error(self, last_error, slave_sql_running_state):
        self.messages.append({
            'status': 'danger',
            'short_message': 'Replication Error',
            'long_message': last_error + 'Current state: %s'
                                         % slave_sql_running_state,
            'time_string':
                datetime.datetime.now().isoformat()
        })

        self.write_lock('danger')

    def track_lag(self, slave_sql_running_state):
        if os.path.isfile('lag.lock'):
            with open('lag.lock', 'r') as f:
                timestamp = int(f.read())
                current_timestamp = int(time.time())
                difference_in_mintues = \
                    (current_timestamp - timestamp) / 60
                if difference_in_mintues >= 5:
                    self.raise_lag_warning(slave_sql_running_state)
        else:
            self.write_lock('lag')

    def raise_lag_warning(self, slave_sql_running_state):
        self.messages.append({
            'status': 'warning',
            'short_message': 'Replication Lag',
            'long_message':
                'The replica is lagging more than 300s'
                'behind master. Current state: %s'
                % slave_sql_running_state,
            'time_string':
                datetime.datetime.now().isoformat()
        })

        self.write_lock('warning')

    def confirm_normality(self):
        if os.path.isfile('danger.lock') or os.path.isfile(
                'warning.lock'):
            self.messages.append({
                'status': 'good',
                'short_message': 'Everything is back to normal',
                'long_message':
                    'Nothing to complain about.',
                'time_string':
                    datetime.datetime.now().isoformat()
            })

        self.clear_locks()

    def raise_exception(self, error):
        self.messages.append({
            'status': 'danger',
            'short_message': 'Exception',
            'long_message': str(error),
            'time_string': datetime.datetime.now().isoformat()
        })

        self.write_lock('danger')

    @staticmethod
    def clear_locks():
        if os.path.isfile('danger.lock'):
            os.remove('danger.lock')
        if os.path.isfile('lag.lock'):
            os.remove('lag.lock')
        if os.path.isfile('warning.lock'):
            os.remove('warning.lock')

    @staticmethod
    def write_lock(status):
        if not os.path.isfile('danger.lock'):
            with open(status + '.lock', 'w') as f:
                f.write(str(int(time.time())))

    def trigger_notifications(self):
        for notifier in self.notifiers:
            for message in self.messages:
                notifier.notify(message['status'], message['short_message'],
                                message['long_message'], message['time_string'])

        self.messages = []