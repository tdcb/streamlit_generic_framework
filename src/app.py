# src/app.py - Refactored for Streamlit in Snowflake (SiS)

import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.exceptions import SnowparkSQLException
import pandas as pd
from datetime import date, datetime
import uuid

# --- Page Configuration ---
st.set_page_config(
    page_title="Streamlit Dynamic UI Framework",
    layout="wide"
)

# Initialize session state
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'current_record_id' not in st.session_state:
    st.session_state.current_record_id = None

# --- Snowflake Session ---
@st.cache_resource
def get_session():
    """Gets the active Snowpark session provided by the SiS environment."""
    return get_active_session()

# --- Configuration Loading ---
@st.cache_data(ttl=3600)
def load_configuration(_session):
    """Loads all UI and workflow configuration from Snowflake tables using a Snowpark session."""
    st.info("Loading application configuration from Snowflake...")
    config = {}
    try:
        config['screens'] = _session.sql("SELECT * FROM SCREENS").to_pandas().set_index('SCREEN_ID')
        config['groups'] = _session.sql("SELECT * FROM SCREEN_GROUPS").to_pandas()
        config['elements'] = _session.sql("SELECT * FROM ELEMENTS").to_pandas().set_index('ELEMENT_ID')
        config['permissions'] = _session.sql("SELECT * FROM ROLE_PERMISSIONS").to_pandas()
        config['workflows'] = _session.sql("SELECT * FROM WORKFLOW_LEVELS").to_pandas()
        config['users'] = _session.sql("SELECT * FROM USERS").to_pandas().set_index('USER_ID')
        st.success("Configuration loaded successfully.")
        return config
    except SnowparkSQLException as e:
        st.error(f"Error loading configuration from Snowflake: {e}")
        return None

# --- Data Fetching Logic ---
@st.cache_data(ttl=60)
def get_records_for_screen(_session, screen_info):
    table_name = screen_info['TARGET_TABLE']
    pk_column = screen_info['UNIQUE_KEY_COLUMN']
    query = f"SELECT {pk_column} FROM {table_name} QUALIFY ROW_NUMBER() OVER (PARTITION BY {pk_column} ORDER BY version DESC) = 1"
    try:
        df = _session.sql(query).to_pandas()
        return df[pk_column.upper()].tolist()
    except SnowparkSQLException as e:
        st.error(f"Error fetching records from table {table_name}: {e}")
        return []

@st.cache_data(ttl=10)
def get_record_data(_session, screen_info, record_id):
    table_name = screen_info['TARGET_TABLE']
    pk_column = screen_info['UNIQUE_KEY_COLUMN']
    query = f"SELECT * FROM {table_name} WHERE {pk_column} = ? ORDER BY version DESC LIMIT 1"
    try:
        df = _session.sql(query, params=[record_id]).to_pandas()
        return df.iloc[0] if not df.empty else None
    except SnowparkSQLException as e:
        st.error(f"Error fetching record data for {record_id}: {e}")
        return None

# --- Data Persistence & Workflow Logic ---
def execute_sql(session, query, params):
    """Helper to execute SQL with parameters."""
    session.sql(query, params=params).collect()

def log_audit(session, record_id, table_name, column_name, old_value, new_value, action_type, user_id, user_role, version, comments=""):
    audit_id = str(uuid.uuid4())
    action_timestamp = datetime.now()
    old_value_str = str(old_value) if old_value is not None else ""
    new_value_str = str(new_value) if new_value is not None else ""
    query = """
        INSERT INTO AUDIT_LOG (audit_id, record_id, table_name, column_name, old_value, new_value, action_type, action_timestamp, user_id, user_role, record_version, comments)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    execute_sql(session, query, [audit_id, record_id, table_name, column_name, old_value_str, new_value_str, action_type, action_timestamp, user_id, user_role, version, comments])

def save_record(session, screen_info, record_id, form_data, user_id, user_role):
    try:
        old_data = get_record_data(session, screen_info, record_id) if record_id != "new" else None

        new_data = form_data.copy()
        new_data['last_updated_by'] = user_id
        new_data['last_updated_at'] = datetime.now()
        action_type = 'UPDATE'

        if record_id == "new":
            new_record_id = str(uuid.uuid4())
            new_version = 1
            action_type = 'INSERT'
            new_data[screen_info['UNIQUE_KEY_COLUMN']] = new_record_id
            new_data.update({'version': 1, 'status': 'DRAFT', 'current_approver_level': 0, 'created_by': user_id, 'created_at': datetime.now()})
        else:
            new_record_id = record_id
            new_version = int(old_data['VERSION']) + 1
            new_data['version'] = new_version
            for col in old_data.index:
                if col.lower() not in new_data: new_data[col.lower()] = old_data[col]

        columns = [c.lower() for c in new_data.keys()]
        placeholders = ", ".join(["?"] * len(columns))
        insert_query = f"INSERT INTO {screen_info['TARGET_TABLE']} ({', '.join(columns)}) VALUES ({placeholders})"
        execute_sql(session, insert_query, list(new_data.values()))

        # Audit logging
        if action_type == 'INSERT':
            for col, val in new_data.items():
                log_audit(session, new_record_id, screen_info['TARGET_TABLE'], col, None, val, action_type, user_id, user_role, new_version)
        else:
            for col, new_val in new_data.items():
                old_val = old_data.get(col.upper())
                if str(old_val) != str(new_val):
                    log_audit(session, new_record_id, screen_info['TARGET_TABLE'], col, old_val, new_val, action_type, user_id, user_role, new_version)

        st.success(f"Record `{new_record_id}` saved successfully as version {new_version}.")
        get_records_for_screen.clear()
        get_record_data.clear()
        st.session_state.current_record_id = new_record_id
        st.session_state.form_data = {}
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Error saving record: {e}")

def update_record_status(session, config, screen_info, record_id, action_type, user_id, user_role, comments=""):
    try:
        old_data = get_record_data(session, screen_info, record_id)
        if old_data is None:
            st.error("Cannot update status of a non-existent record."); return

        new_version = int(old_data['VERSION']) + 1
        new_data = {k.lower(): v for k, v in old_data.to_dict().items()}
        new_data.update({'version': new_version, 'last_updated_by': user_id, 'last_updated_at': datetime.now()})

        old_status = old_data['STATUS']
        current_level = int(old_data['CURRENT_APPROVER_LEVEL'])
        workflow_id = 'VENDOR_WF'
        max_level = config['workflows'][config['workflows']['WORKFLOW_ID'] == workflow_id]['LEVEL_NUM'].max()

        if action_type == 'SUBMIT':
            new_data.update({'status': 'PENDING_L1', 'current_approver_level': 1})
        elif action_type == 'APPROVE':
            new_data['current_approver_level'] = current_level + 1
            new_data['status'] = 'APPROVED' if current_level >= max_level else f'PENDING_L{current_level + 1}'
        elif action_type == 'REJECT':
            new_data.update({'status': 'DRAFT', 'current_approver_level': 0})

        columns = new_data.keys()
        placeholders = ", ".join(["?"] * len(columns))
        insert_query = f"INSERT INTO {screen_info['TARGET_TABLE']} ({', '.join(columns)}) VALUES ({placeholders})"
        execute_sql(session, insert_query, list(new_data.values()))

        log_audit(session, record_id, screen_info['TARGET_TABLE'], 'status', old_status, new_data['status'], action_type, user_id, user_role, new_version, comments)

        st.success(f"Record action '{action_type}' completed. New status: `{new_data['status']}`.")
        get_record_data.clear()
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Error updating status: {e}")

# --- UI Rendering Engine ---
# (render_element and render_screen logic is largely the same, just needs session passed instead of conn)
def has_permission(element_id, user_role, permissions_df, permission_type):
    if permission_type not in ['CAN_READ', 'CAN_WRITE']: return False
    permission = permissions_df[(permissions_df['ELEMENT_ID'] == element_id) & (permissions_df['ROLE_NAME'] == user_role)]
    return permission.iloc[0][permission_type] if not permission.empty else False

def render_element(session, config, screen_info, element, user_role, record_data):
    element_id = element.name
    if not has_permission(element_id, user_role, config['permissions'], 'CAN_READ'): return

    is_disabled = not has_permission(element_id, user_role, config['permissions'], 'CAN_WRITE')
    db_column, element_type, label = element['DB_COLUMN'], element['ELEMENT_TYPE'], element['LABEL']
    key = f"{element_id}_{st.session_state.current_record_id or 'new'}"

    if element_type == 'button':
        record_id, status, user_id = st.session_state.current_record_id, (record_data['STATUS'].upper() if record_data is not None else 'DRAFT'), st.session_state.user_id
        render = False
        if label == 'Save Draft' and (status == 'DRAFT' or record_id == 'new'): render = True
        elif label == 'Submit for Approval' and status == 'DRAFT' and record_id != 'new': render = True
        elif label in ['Approve', 'Reject'] and 'PENDING' in status:
            wf_id, current_level = 'VENDOR_WF', record_data['CURRENT_APPROVER_LEVEL']
            required_role = config['workflows'][(config['workflows']['WORKFLOW_ID'] == wf_id) & (config['workflows']['LEVEL_NUM'] == current_level)]
            if not required_role.empty and user_role == required_role.iloc[0]['ROLE_NAME']: render = True

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
        # Prioritize declarative configuration for options
        if pd.notna(element['OPTIONS_SOURCE_TABLE']) and element['OPTIONS_SOURCE_TABLE']:
            query = f"SELECT {element['OPTIONS_VALUE_COLUMN']}, {element['OPTIONS_LABEL_COLUMN']} FROM {element['OPTIONS_SOURCE_TABLE']}"
        # Fallback to custom query
        elif pd.notna(element['OPTIONS_QUERY']) and element['OPTIONS_QUERY']:
            query = element['OPTIONS_QUERY']

        options = {}
        if query:
            options_df = session.sql(query).to_pandas()
            # Use first col for value, second for label if it exists, otherwise first for both
            value_col = options_df.columns[0]
            label_col = options_df.columns[1] if len(options_df.columns) > 1 else value_col
            options = options_df.set_index(value_col)[label_col].to_dict()

        if element_type == 'dropdown':
            # The value stored in the DB is the key in our options dict
            option_keys = list(options.keys())
            try:
                current_index = option_keys.index(current_value)
            except (ValueError, TypeError):
                current_index = 0

            new_value = st.selectbox(
                label,
                options=option_keys,
                format_func=lambda x: options.get(x, str(x)),
                index=current_index,
                disabled=is_disabled,
                key=key
            )
            st.session_state.form_data[db_column] = new_value
        else:  # multiselect
            default = current_value.split(',') if isinstance(current_value, str) else []
            selected_values = st.multiselect(
                label,
                options=options.keys(),
                format_func=lambda x: options.get(x, str(x)),
                default=default,
                disabled=is_disabled,
                key=key
            )
            st.session_state.form_data[db_column] = ",".join(selected_values)

def render_screen(session, config, screen_id, user_role, record_data):
    screen_info = config['screens'].loc[screen_id]
    st.header(screen_info['SCREEN_NAME'])
    st.caption(screen_info['DESCRIPTION'])
    screen_groups = config['groups'][config['groups']['SCREEN_ID'] == screen_id].sort_values('DISPLAY_ORDER')
    for _, group in screen_groups.iterrows():
        with st.expander(group['GROUP_NAME'], expanded=True):
            elements = config['elements'][config['elements']['GROUP_ID'] == group['GROUP_ID']].sort_values('DISPLAY_ORDER')
            for _, element in elements.iterrows():
                render_element(session, config, screen_info, element, user_role, record_data)

# --- Main Application Logic ---
def main():
    st.title("📄 Streamlit Dynamic UI Framework")
    session = get_session()
    config = load_configuration(session)
    if config is None: return

    # --- Authentication from Snowflake Session ---
    st.session_state.user_id = session.get_current_user().replace("'", "")
    # Find the application role from the user's current Snowflake role
    sf_role = session.get_current_role().replace("'", "")
    user_roles = config['users'][config['users']['USER_NAME'].str.upper() == st.session_state.user_id.upper()]

    # This is a simplification. A real app might map SF roles to app roles more robustly.
    # Here we assume the user_id is the user's name in the USERS table.
    app_user = config['users'][config['users'].index.str.upper() == st.session_state.user_id.upper()]
    if not app_user.empty:
        st.session_state.user_role = app_user.iloc[0]['ROLE_NAME']
    else:
        st.error(f"User '{st.session_state.user_id}' not found in the application's USERS table. Please add this user."); return

    st.sidebar.title("👤 User Information")
    st.sidebar.write(f"User: **{st.session_state.user_id}**")
    st.sidebar.write(f"Role: **{st.session_state.user_role}**")
    st.sidebar.divider()

    # --- Screen and Record Navigation ---
    st.sidebar.title("⚙️ Navigation")
    user_perms = config['permissions'][(config['permissions']['ROLE_NAME'] == st.session_state.user_role) & (config['permissions']['CAN_READ'])]
    visible_elements = config['elements'][config['elements'].index.isin(user_perms['ELEMENT_ID'])]
    visible_groups = config['groups'][config['groups']['GROUP_ID'].isin(visible_elements['GROUP_ID'])]
    visible_screen_ids = visible_groups['SCREEN_ID'].unique()

    screen_options = {sid: name for sid, name in config['screens']['SCREEN_NAME'].items() if sid in visible_screen_ids}
    if not screen_options: st.info("No screens available for your role."); return
    selected_screen_id = st.sidebar.selectbox("Select a screen:", options=list(screen_options.keys()), format_func=lambda x: screen_options[x])

    if not selected_screen_id: return
    screen_info = config['screens'].loc[selected_screen_id]

    if st.sidebar.button("➕ New Record"):
        st.session_state.current_record_id = "new"
        st.session_state.form_data = {}; st.experimental_rerun()

    record_list = get_records_for_screen(session, screen_info)
    record_options = ["new"] + record_list

    try: current_index = record_options.index(st.session_state.current_record_id)
    except (ValueError, AttributeError): current_index = 0

    selected_record_id = st.sidebar.selectbox("Select a record:", options=record_options, index=current_index)

    if st.session_state.current_record_id != selected_record_id:
        st.session_state.current_record_id = selected_record_id
        st.session_state.form_data = {}; st.experimental_rerun()

    record_data = None
    if selected_record_id != "new":
        record_data = get_record_data(session, screen_info, selected_record_id)
        if not st.session_state.form_data and record_data is not None:
            st.session_state.form_data = {k.upper(): v for k, v in record_data.to_dict().items()}

    render_screen(session, config, selected_screen_id, st.session_state.user_role, record_data)

if __name__ == "__main__":
    main()
