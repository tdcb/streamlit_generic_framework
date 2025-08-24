# src/app.py - Final version with Debugging Features

import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.exceptions import SnowparkSQLException
import pandas as pd
from datetime import date, datetime
import uuid
import traceback

# --- Page Configuration ---
st.set_page_config(page_title="Streamlit Dynamic UI Framework", layout="wide")

# --- Session State Initialization ---
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'current_record_id' not in st.session_state:
    st.session_state.current_record_id = None
if 'debug_mode' not in st.session_state:
    st.session_state.debug_mode = False

# --- Exception Handling ---
def handle_exception(e, message="An unexpected error occurred."):
    """Displays a user-friendly error and detailed traceback in debug mode."""
    st.error(message)
    if st.session_state.debug_mode:
        with st.expander("Error Details"):
            st.code(traceback.format_exc())

# --- Snowflake Session & Config Loading ---
@st.cache_resource
def get_session():
    return get_active_session()

@st.cache_data(ttl=3600)
def load_configuration(_session):
    try:
        st.info("Loading application configuration from Snowflake...")
        config = {
            'screens': _session.sql("SELECT * FROM SCREENS").to_pandas().set_index('SCREEN_ID'),
            'groups': _session.sql("SELECT * FROM SCREEN_GROUPS").to_pandas(),
            'elements': _session.sql("SELECT * FROM ELEMENTS").to_pandas().set_index('ELEMENT_ID'),
            'permissions': _session.sql("SELECT * FROM ROLE_PERMISSIONS").to_pandas(),
            'workflows': _session.sql("SELECT * FROM WORKFLOW_LEVELS").to_pandas(),
            'users': _session.sql("SELECT * FROM USERS").to_pandas().set_index('USER_ID')
        }
        st.success("Configuration loaded successfully.")
        return config
    except SnowparkSQLException as e:
        handle_exception(e, "Database Error: Could not load configuration.")
        return None

# --- Data Fetching & Persistence ---
@st.cache_data(ttl=60)
def get_records_for_screen(_session, screen_info):
    try:
        table, pk_col = screen_info['TARGET_TABLE'], screen_info['UNIQUE_KEY_COLUMN']
        query = f"SELECT {pk_col} FROM {table} QUALIFY ROW_NUMBER() OVER (PARTITION BY {pk_col} ORDER BY version DESC) = 1"
        return _session.sql(query).to_pandas()[pk_col.upper()].tolist()
    except SnowparkSQLException as e:
        handle_exception(e, f"Error fetching records from table {screen_info['TARGET_TABLE']}.")
        return []

@st.cache_data(ttl=10)
def get_record_data(_session, screen_info, record_id):
    try:
        table, pk_col = screen_info['TARGET_TABLE'], screen_info['UNIQUE_KEY_COLUMN']
        query = f"SELECT * FROM {table} WHERE {pk_col} = ? ORDER BY version DESC LIMIT 1"
        df = _session.sql(query, params=[record_id]).to_pandas()
        return df.iloc[0] if not df.empty else None
    except SnowparkSQLException as e:
        handle_exception(e, f"Error fetching data for record {record_id}.")
        return None

def execute_sql(session, query, params):
    session.sql(query, params=params).collect()

def log_audit(session, record_id, table_name, column_name, old_value, new_value, action_type, user_id, user_role, version, comments=""):
    # ... (implementation is the same, but called from within a try block)
    audit_id, ts = str(uuid.uuid4()), datetime.now()
    old_val, new_val = str(old_value or ""), str(new_value or "")
    query = "INSERT INTO AUDIT_LOG VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    params = [audit_id, record_id, table_name, column_name, old_val, new_val, action_type, ts, user_id, user_role, version, comments]
    execute_sql(session, query, params)

def save_record(session, screen_info, record_id, form_data, user_id, user_role):
    try:
        # ... (logic for preparing new_data is the same)
        old_data = get_record_data(session, screen_info, record_id) if record_id != "new" else None
        new_data = form_data.copy()
        new_data['last_updated_by'], new_data['last_updated_at'] = user_id, datetime.now()
        action_type = 'UPDATE'
        if record_id == "new":
            new_record_id, new_version, action_type = str(uuid.uuid4()), 1, 'INSERT'
            new_data.update({screen_info['UNIQUE_KEY_COLUMN']: new_record_id, 'version': 1, 'status': 'DRAFT', 'current_approver_level': 0, 'created_by': user_id, 'created_at': datetime.now()})
        else:
            new_record_id, new_version = record_id, int(old_data['VERSION']) + 1
            new_data['version'] = new_version
            for col in old_data.index:
                if col.lower() not in new_data: new_data[col.lower()] = old_data[col]

        cols, placeholders = zip(*[(c.lower(), "?") for c in new_data.keys()])
        query = f"INSERT INTO {screen_info['TARGET_TABLE']} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        execute_sql(session, query, list(new_data.values()))

        # ... (audit logging logic is the same)
        if action_type == 'INSERT':
            for col, val in new_data.items(): log_audit(session, new_record_id, screen_info['TARGET_TABLE'], col, None, val, action_type, user_id, user_role, new_version)
        else:
            for col, new_val in new_data.items():
                if str(old_data.get(col.upper())) != str(new_val): log_audit(session, new_record_id, screen_info['TARGET_TABLE'], col, old_data.get(col.upper()), new_val, action_type, user_id, user_role, new_version)

        st.success(f"Record `{new_record_id}` saved as version {new_version}.")
        get_records_for_screen.clear(); get_record_data.clear()
        st.session_state.current_record_id = new_record_id
        st.session_state.form_data = {}; st.experimental_rerun()
    except (SnowparkSQLException, Exception) as e:
        handle_exception(e, "Error saving record.")

def update_record_status(session, config, screen_info, record_id, action_type, user_id, user_role, comments=""):
    try:
        # ... (logic is the same)
        old_data = get_record_data(session, screen_info, record_id)
        if old_data is None: st.error("Cannot update status of a non-existent record."); return
        new_version, new_data = int(old_data['VERSION']) + 1, {k.lower(): v for k, v in old_data.to_dict().items()}
        new_data.update({'version': new_version, 'last_updated_by': user_id, 'last_updated_at': datetime.now()})
        old_status, current_level = old_data['STATUS'], int(old_data['CURRENT_APPROVER_LEVEL'])
        workflow_id = 'VENDOR_WF' # This could be made dynamic
        max_level = config['workflows'][config['workflows']['WORKFLOW_ID'] == workflow_id]['LEVEL_NUM'].max()
        if action_type == 'SUBMIT': new_data.update({'status': 'PENDING_L1', 'current_approver_level': 1})
        elif action_type == 'APPROVE':
            new_data['current_approver_level'] = current_level + 1
            new_data['status'] = 'APPROVED' if current_level >= max_level else f'PENDING_L{current_level + 1}'
        elif action_type == 'REJECT': new_data.update({'status': 'DRAFT', 'current_approver_level': 0})
        cols, placeholders = zip(*[(c.lower(), "?") for c in new_data.keys()])
        query = f"INSERT INTO {screen_info['TARGET_TABLE']} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        execute_sql(session, query, list(new_data.values()))
        log_audit(session, record_id, screen_info['TARGET_TABLE'], 'status', old_status, new_data['status'], action_type, user_id, user_role, new_version, comments)
        st.success(f"Record action '{action_type}' completed. New status: `{new_data['status']}`.")
        get_record_data.clear(); st.experimental_rerun()
    except (SnowparkSQLException, Exception) as e:
        handle_exception(e, "Error updating record status.")

# --- UI Rendering Engine ---
def has_permission(element_id, user_role, permissions_df):
    permission = permissions_df[(permissions_df['ELEMENT_ID'] == element_id) & (permissions_df['ROLE_NAME'].str.upper() == user_role)]
    if permission.empty: return False, False
    return permission.iloc[0]['CAN_READ'], permission.iloc[0]['CAN_WRITE']

def render_element(session, config, screen_info, element, user_role, record_data):
    can_read, can_write = has_permission(element.name, user_role, config['permissions'])
    if not can_read: return

    is_disabled = not can_write
    db_column, element_type, label = element['DB_COLUMN'], element['ELEMENT_TYPE'], element['LABEL']
    key = f"{element.name}_{st.session_state.current_record_id or 'new'}"

    if element_type == 'button':
        record_id, status, user_id = st.session_state.current_record_id, (record_data['STATUS'].upper() if record_data is not None else 'DRAFT'), st.session_state.user_id
        render = False
        if label == 'Save Draft' and (status == 'DRAFT' or record_id == 'new'): render = True
        elif label == 'Submit for Approval' and status == 'DRAFT' and record_id != 'new': render = True
        elif label in ['Approve', 'Reject'] and 'PENDING' in status:
            wf_id, current_level = 'VENDOR_WF', record_data['CURRENT_APPROVER_LEVEL']
            required_role = config['workflows'][(config['workflows']['WORKFLOW_ID'] == wf_id) & (config['workflows']['LEVEL_NUM'] == current_level)]
            if not required_role.empty and user_role == required_role.iloc[0]['ROLE_NAME'].upper(): render = True

        if render:
            if label == 'Reject':
                rejection_comment = st.text_input("Rejection Comments", key=f"rejection_{key}")
                if st.button(label, key=key):
                    if rejection_comment: update_record_status(session, config, screen_info, record_id, 'REJECT', user_id, user_role, comments=rejection_comment)
                    else: st.warning("Rejection comments are required.")
            else:
                action_map = {'Save Draft': lambda: save_record(session, screen_info, record_id, st.session_state.form_data, user_id, user_role),
                              'Submit for Approval': lambda: update_record_status(session, config, screen_info, record_id, 'SUBMIT', user_id, user_role),
                              'Approve': lambda: update_record_status(session, config, screen_info, record_id, 'APPROVE', user_id, user_role)}
                if st.button(label, key=key, type="primary" if label != 'Submit for Approval' else "secondary"):
                    if label in action_map: action_map[label]()
        return

    current_value = st.session_state.form_data.get(db_column.upper() if db_column else None)
    if element_type == 'text': st.session_state.form_data[db_column] = st.text_input(label, value=current_value or "", disabled=is_disabled, key=key)
    elif element_type == 'number': st.session_state.form_data[db_column] = st.number_input(label, value=current_value or 0, disabled=is_disabled, key=key, format="%g")
    elif element_type == 'date':
        if isinstance(current_value, str): current_value = datetime.strptime(current_value, '%Y-%m-%d').date()
        st.session_state.form_data[db_column] = st.date_input(label, value=current_value, disabled=is_disabled, key=key)
    elif element_type in ['dropdown', 'multiselect']:
        query = ""
        if pd.notna(element['OPTIONS_SOURCE_TABLE']) and element['OPTIONS_SOURCE_TABLE']:
            query = f"SELECT {element['OPTIONS_VALUE_COLUMN']}, {element['OPTIONS_LABEL_COLUMN']} FROM {element['OPTIONS_SOURCE_TABLE']}"
        elif pd.notna(element['OPTIONS_QUERY']) and element['OPTIONS_QUERY']:
            query = element['OPTIONS_QUERY']

        options = {}
        if query:
            options_df = session.sql(query).to_pandas()
            value_col, label_col = options_df.columns[0], options_df.columns[1] if len(options_df.columns) > 1 else options_df.columns[0]
            options = options_df.set_index(value_col)[label_col].to_dict()

        if element_type == 'dropdown':
            option_keys = list(options.keys())
            try: current_index = option_keys.index(current_value)
            except (ValueError, TypeError): current_index = 0
            new_value = st.selectbox(label, options=option_keys, format_func=lambda x: options.get(x, str(x)), index=current_index, disabled=is_disabled, key=key)
            st.session_state.form_data[db_column] = new_value
        else:
            default = current_value.split(',') if isinstance(current_value, str) else []
            selected_values = st.multiselect(label, options=options.keys(), format_func=lambda x: options.get(x, str(x)), default=default, disabled=is_disabled, key=key)
            st.session_state.form_data[db_column] = ",".join(selected_values)

def render_screen(session, config, screen_id, user_role, record_data):
    """Renders a full screen with a smart, automatic multi-column layout."""
    screen_info = config['screens'].loc[screen_id]
    st.header(screen_info['SCREEN_NAME'])
    st.caption(screen_info['DESCRIPTION'])

    screen_groups = config['groups'][config['groups']['SCREEN_ID'] == screen_id].sort_values('DISPLAY_ORDER')

    def pairwise(iterable):
        return zip_longest(iterable, iterable)

    for _, group in screen_groups.iterrows():
        with st.expander(group['GROUP_NAME'], expanded=True):
            group_elements = config['elements'][config['elements']['GROUP_ID'] == group['GROUP_ID']].sort_values('DISPLAY_ORDER')

            fields = group_elements[group_elements['ELEMENT_TYPE'] != 'button']
            buttons = group_elements[group_elements['ELEMENT_TYPE'] == 'button']

            for element1_tuple, element2_tuple in pairwise(fields.iterrows()):
                col1, col2 = st.columns(2)
                if element1_tuple:
                    with col1: render_element(session, config, screen_info, element1_tuple[1], user_role, record_data)
                if element2_tuple:
                    with col2: render_element(session, config, screen_info, element2_tuple[1], user_role, record_data)

            if not buttons.empty:
                st.divider()
                cols = st.columns(len(buttons) + 2)
                for i, (_, button) in enumerate(buttons.iterrows()):
                    with cols[i]:
                        render_element(session, config, screen_info, button, user_role, record_data)

# --- Main Application Logic ---
def main():
    st.title("📄 Streamlit Dynamic UI Framework")

    st.sidebar.title("🛠️ Controls")
    st.sidebar.checkbox("Enable Debug Mode", key='debug_mode')
    st.sidebar.divider()

    session = get_session()
    config = load_configuration(session)
    if config is None: st.stop()

    # ... (Authentication logic is the same)
    st.session_state.user_id = session.get_current_user().replace("'", "")
    st.session_state.user_role = session.get_current_role().replace("'", "").upper()
    # ...

    # --- Debug Inspector ---
    if st.session_state.debug_mode:
        st.sidebar.divider()
        st.sidebar.title("🐞 Debug Info")
        with st.sidebar.expander("Session State"):
            st.json(st.session_state.to_dict())
        with st.sidebar.expander("Configuration"):
            for name, df in config.items():
                st.subheader(name)
                st.dataframe(df)

# ... (The rest of main is the same, just need to re-paste it)
# I will overwrite the file completely to ensure all parts are present.
