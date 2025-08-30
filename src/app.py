# src/app.py - Final version with Multi-Table, Auto-Layout, and Debugging

import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.exceptions import SnowparkSQLException
import pandas as pd
from datetime import datetime
import uuid
import traceback
from itertools import zip_longest

# --- Page Configuration & State ---
st.set_page_config(page_title="Streamlit Dynamic UI Framework", layout="wide")
if 'form_data' not in st.session_state: st.session_state.form_data = {}
if 'current_record_id' not in st.session_state: st.session_state.current_record_id = None
if 'debug_mode' not in st.session_state: st.session_state.debug_mode = False

# --- Exception Handling & Snowflake Session ---
def handle_exception(e, message="An unexpected error occurred."):
    st.error(message, icon="🚨")
    if st.session_state.debug_mode:
        with st.expander("Error Details (Debug Mode)"): st.code(traceback.format_exc())

@st.cache_resource
def get_session():
    try: return get_active_session()
    except Exception: st.error("Could not get active Snowflake session."); return None

# --- Configuration & Data Loading ---
@st.cache_data(ttl=3600)
def load_configuration(_session):
    try:
        st.info("Loading application configuration...")
        config = {
            'screens': _session.sql("SELECT * FROM SCREENS").to_pandas().set_index('SCREEN_ID'),
            'groups': _session.sql("SELECT * FROM SCREEN_GROUPS").to_pandas(),
            'elements': _session.sql("SELECT * FROM ELEMENTS").to_pandas().set_index('ELEMENT_ID'),
            'permissions': _session.sql("SELECT * FROM ROLE_PERMISSIONS").to_pandas(),
            'workflows': _session.sql("SELECT * FROM WORKFLOW_LEVELS").to_pandas(),
            'users': _session.sql("SELECT * FROM USERS").to_pandas().set_index('USER_ID')
        }
        st.success("Configuration loaded.")
        return config
    except SnowparkSQLException as e:
        handle_exception(e, "Database Error: Could not load configuration."); return None

@st.cache_data(ttl=60)
def get_records_for_screen(_session, screen_info):
    try:
        table, pk_col = screen_info['TARGET_TABLE'], screen_info['UNIQUE_KEY_COLUMN']
        query = f"SELECT {pk_col} FROM {table} QUALIFY ROW_NUMBER() OVER (PARTITION BY {pk_col} ORDER BY version DESC) = 1"
        return _session.sql(query).to_pandas()[pk_col.upper()].tolist()
    except Exception as e:
        handle_exception(e, f"Error fetching records from table {screen_info['TARGET_TABLE']}."); return []

@st.cache_data(ttl=10)
def get_record_data(_session, config, screen_info, record_id):
    """Fetches data from multiple tables for a single record and merges it."""
    try:
        primary_table, pk_col = screen_info['TARGET_TABLE'], screen_info['UNIQUE_KEY_COLUMN']
        query = f"SELECT * FROM {primary_table} WHERE {pk_col} = ? ORDER BY version DESC LIMIT 1"
        primary_df = _session.sql(query, params=[record_id]).to_pandas()
        if primary_df.empty: return None

        merged_data = primary_df.iloc[0].copy()

        screen_groups = config['groups'][config['groups']['SCREEN_ID'] == screen_info.name]
        screen_elements = config['elements'][config['elements']['GROUP_ID'].isin(screen_groups['GROUP_ID'])]
        secondary_tables = screen_elements['TARGET_TABLE'].dropna().unique()

        for table in secondary_tables:
            if table.upper() != primary_table.upper():
                query = f"SELECT * FROM {table} WHERE {pk_col} = ?"
                secondary_df = _session.sql(query, params=[record_id]).to_pandas()
                if not secondary_df.empty:
                    merged_data = pd.concat([merged_data, secondary_df.iloc[0].drop(pk_col.upper(), errors='ignore')])
        return merged_data
    except Exception as e:
        handle_exception(e, f"Error fetching data for record {record_id}."); return None

# --- Data Persistence ---
def execute_sql(session, query, params):
    session.sql(query, params=params).collect()

def log_audit(session, record_id, table_name, column_name, old_value, new_value, action_type, user_id, user_role, version, comments=""):
    audit_id, ts = str(uuid.uuid4()), datetime.now()
    old_val, new_val = str(old_value or ""), str(new_value or "")
    query = "INSERT INTO AUDIT_LOG (AUDIT_ID, RECORD_ID, TABLE_NAME, COLUMN_NAME, OLD_VALUE, NEW_VALUE, ACTION_TYPE, ACTION_TIMESTAMP, USER_ID, USER_ROLE, RECORD_VERSION, COMMENTS) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    params = [audit_id, record_id, table_name, column_name, old_val, new_val, action_type, ts, user_id, user_role, version, comments]
    execute_sql(session, query, params)

def save_record(session, config, screen_info, record_id, form_data, user_id, user_role):
    try:
        screen_groups = config['groups'][config['groups']['SCREEN_ID'] == screen_info.name]
        screen_elements = config['elements'][config['elements']['GROUP_ID'].isin(screen_groups['GROUP_ID'])]
        primary_table, pk_col = screen_info['TARGET_TABLE'], screen_info['UNIQUE_KEY_COLUMN']

        data_by_table = {}
        for _, element_config in screen_elements.iterrows():
            if pd.notna(element_config['DB_COLUMN']):
                table = (element_config.get('TARGET_TABLE') or primary_table).upper()
                if table not in data_by_table: data_by_table[table] = {}
                db_col_lower = element_config['DB_COLUMN'].lower()
                if db_col_lower in form_data:
                    data_by_table[table][db_col_lower] = form_data[db_col_lower]

        primary_data = data_by_table.get(primary_table.upper(), {})
        old_data = get_record_data(session, config, screen_info, record_id) if record_id != "new" else None

        primary_data['last_updated_by'], primary_data['last_updated_at'] = user_id, datetime.now()

        if record_id == "new":
            new_record_id, new_version = str(uuid.uuid4()), 1
            primary_data.update({pk_col.lower(): new_record_id, 'version': 1, 'status': 'DRAFT', 'current_approver_level': 0, 'created_by': user_id, 'created_at': datetime.now()})
        else:
            new_record_id, new_version = record_id, int(old_data['VERSION']) + 1
            primary_data['version'] = new_version
            for col in old_data.index:
                if col.lower() not in primary_data: primary_data[col.lower()] = old_data[col]

        cols, placeholders = zip(*[(c, "?") for c in primary_data.keys()])
        query = f"INSERT INTO {primary_table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        execute_sql(session, query, list(primary_data.values()))

        for table, data in data_by_table.items():
            if table.upper() != primary_table.upper():
                data[pk_col.lower()], data['last_updated_by'], data['last_updated_at'] = new_record_id, user_id, datetime.now()
                update_cols = [f"{col} = :{col}" for col in data.keys() if col.lower() != pk_col.lower()]
                insert_cols, insert_binds = ", ".join(data.keys()), ", ".join([f":{c}" for c in data.keys()])
                merge_sql = f"MERGE INTO {table} t USING (SELECT '{new_record_id}' as {pk_col}) s ON t.{pk_col} = s.{pk_col} WHEN MATCHED THEN UPDATE SET {', '.join(update_cols)} WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_binds})"
                session.sql(merge_sql, params=data).collect()

        st.success(f"Record `{new_record_id}` saved successfully.")
        get_records_for_screen.clear(); get_record_data.clear()
        st.session_state.current_record_id = new_record_id
        st.session_state.form_data = {}; st.experimental_rerun()
    except (SnowparkSQLException, Exception) as e:
        handle_exception(e, "Error saving record.")

def update_record_status(session, config, screen_info, record_id, action_type, user_id, user_role, comments=""):
    try:
        old_data = get_record_data(session, config, screen_info, record_id)
        if old_data is None: st.error("Cannot update status."); return
        primary_table, pk_col = screen_info['TARGET_TABLE'], screen_info['UNIQUE_KEY_COLUMN']
        new_version, new_data = int(old_data['VERSION']) + 1, {k.lower(): v for k, v in old_data.to_dict().items()}
        new_data.update({'version': new_version, 'last_updated_by': user_id, 'last_updated_at': datetime.now()})
        old_status, current_level = old_data['STATUS'], int(old_data['CURRENT_APPROVER_LEVEL'])
        workflow_id = 'VENDOR_WF'
        max_level = config['workflows'][config['workflows']['WORKFLOW_ID'] == workflow_id]['LEVEL_NUM'].max()
        if action_type == 'SUBMIT': new_data.update({'status': 'PENDING_L1', 'current_approver_level': 1})
        elif action_type == 'APPROVE':
            new_data['current_approver_level'] = current_level + 1
            new_data['status'] = 'APPROVED' if current_level >= max_level else f'PENDING_L{current_level + 1}'
        elif action_type == 'REJECT': new_data.update({'status': 'DRAFT', 'current_approver_level': 0})

        cols, placeholders = zip(*[(c, "?") for c in new_data.keys() if c.lower() in old_data.index.str.lower()])
        query = f"INSERT INTO {primary_table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
        execute_sql(session, query, [new_data[c] for c in cols])

        log_audit(session, record_id, primary_table, 'status', old_status, new_data['status'], action_type, user_id, user_role, new_version, comments)
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
                action_map = {'Save Draft': lambda: save_record(session, config, screen_info, record_id, st.session_state.form_data, user_id, user_role),
                              'Submit for Approval': lambda: update_record_status(session, config, screen_info, record_id, 'SUBMIT', user_id, user_role),
                              'Approve': lambda: update_record_status(session, config, screen_info, record_id, 'APPROVE', user_id, user_role)}
                if st.button(label, key=key, type="primary" if label != 'Submit for Approval' else "secondary"):
                    if label in action_map: action_map[label]()
        return

    current_value = st.session_state.form_data.get(db_column.lower() if db_column else None)
    if element_type == 'text': st.session_state.form_data[db_column.lower()] = st.text_input(label, value=current_value or "", disabled=is_disabled, key=key)
    elif element_type == 'number': st.session_state.form_data[db_column.lower()] = st.number_input(label, value=float(current_value or 0), disabled=is_disabled, key=key, format="%g")
    elif element_type == 'date':
        if isinstance(current_value, str): current_value = datetime.strptime(current_value, '%Y-%m-%d').date()
        st.session_state.form_data[db_column.lower()] = st.date_input(label, value=current_value, disabled=is_disabled, key=key)
    elif element_type in ['dropdown', 'multiselect']:
        query = ""
        if pd.notna(element['OPTIONS_SOURCE_TABLE']) and element['OPTIONS_SOURCE_TABLE']:
            query = f"SELECT {element['OPTIONS_VALUE_COLUMN']}, {element['OPTIONS_LABEL_COLUMN']} FROM {element['OPTIONS_SOURCE_TABLE']}"
        elif pd.notna(element['OPTIONS_QUERY']) and element['OPTIONS_QUERY']: query = element['OPTIONS_QUERY']
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
            st.session_state.form_data[db_column.lower()] = new_value
        else:
            default = current_value.split(',') if isinstance(current_value, str) else []
            selected = st.multiselect(label, options=options.keys(), format_func=lambda x: options.get(x, str(x)), default=default, disabled=is_disabled, key=key)
            st.session_state.form_data[db_column.lower()] = ",".join(selected)

def render_screen(session, config, screen_id, user_role, record_data):
    screen_info = config['screens'].loc[screen_id]
    st.header(screen_info['SCREEN_NAME']); st.caption(screen_info['DESCRIPTION'])
    screen_groups = config['groups'][config['groups']['SCREEN_ID'] == screen_id].sort_values('DISPLAY_ORDER')
    def pairwise(iterable): return zip_longest(iterable, iterable)
    for _, group in screen_groups.iterrows():
        with st.expander(group['GROUP_NAME'], expanded=True):
            group_elements = config['elements'][config['elements']['GROUP_ID'] == group['GROUP_ID']].sort_values('DISPLAY_ORDER')
            fields = group_elements[group_elements['ELEMENT_TYPE'] != 'button']
            buttons = group_elements[group_elements['ELEMENT_TYPE'] == 'button']
            for e1_tuple, e2_tuple in pairwise(fields.iterrows()):
                col1, col2 = st.columns(2)
                if e1_tuple:
                    with col1: render_element(session, config, screen_info, e1_tuple[1], user_role, record_data)
                if e2_tuple:
                    with col2: render_element(session, config, screen_info, e2_tuple[1], user_role, record_data)
            if not buttons.empty:
                st.divider()
                cols = st.columns(len(buttons) + 2)
                for i, (_, button) in enumerate(buttons.iterrows()):
                    with cols[i]: render_element(session, config, screen_info, button, user_role, record_data)

# --- Main Application Logic ---
def main():
    st.title("📄 Streamlit Dynamic UI Framework")
    st.sidebar.title("🛠️ Controls"); st.sidebar.checkbox("Enable Debug Mode", key='debug_mode'); st.sidebar.divider()
    session = get_session()
    if session is None: st.stop()
    config = load_configuration(session)
    if config is None: st.stop()
    st.sidebar.title("👤 User Information")
    st.session_state.user_id = session.get_current_user().replace("'", "")
    st.session_state.user_role = session.get_current_role().replace("'", "").upper()
    app_user = config['users'][config['users'].index.str.upper() == st.session_state.user_id.upper()]
    display_name = app_user.iloc[0]['USER_NAME'] if not app_user.empty else st.session_state.user_id
    st.sidebar.write(f"User: **{display_name}**"); st.sidebar.write(f"Active Role: **{st.session_state.user_role}**"); st.sidebar.divider()
    if st.session_state.user_role not in config['permissions']['ROLE_NAME'].str.upper().unique():
        st.warning(f"Your role '{st.session_state.user_role}' has no permissions."); st.stop()
    st.sidebar.title("⚙️ Navigation")
    user_perms = config['permissions'][(config['permissions']['ROLE_NAME'].str.upper() == st.session_state.user_role) & (config['permissions']['CAN_READ'])]
    visible_elements = config['elements'][config['elements'].index.isin(user_perms['ELEMENT_ID'])]
    visible_groups = config['groups'][config['groups']['GROUP_ID'].isin(visible_elements['GROUP_ID'])]
    visible_screen_ids = visible_groups['SCREEN_ID'].unique()
    screen_options = {sid: name for sid, name in config['screens']['SCREEN_NAME'].items() if sid in visible_screen_ids}
    if not screen_options: st.info("No screens available for your role."); st.stop()
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
        record_data = get_record_data(session, config, screen_info, selected_record_id)
        if record_data is not None and not st.session_state.form_data:
            st.session_state.form_data = {k.lower(): v for k, v in record_data.to_dict().items()}
    render_screen(session, config, selected_screen_id, st.session_state.user_role, record_data)
    if st.session_state.debug_mode:
        st.sidebar.divider(); st.sidebar.title("🐞 Debug Info")
        with st.sidebar.expander("Session State"): st.json({k: str(v) for k, v in st.session_state.items()})
        with st.sidebar.expander("Configuration"):
            for name, df in config.items(): st.subheader(name); st.dataframe(df)

if __name__ == "__main__":
    try: main()
    except Exception as e: handle_exception(e, "A critical error occurred in the main application.")
