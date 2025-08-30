-- ----------------------------------------------------------------------------
-- Sample Data for Streamlit Dynamic UI Framework (v5 - Multi-Table)
-- ----------------------------------------------------------------------------
-- This script is re-runnable and includes data for two screens.
-- The Vendor Onboarding screen now demonstrates multi-table data entry.

-- ----------------------------------------------------------------------------
-- Clean Slate
-- ----------------------------------------------------------------------------
DELETE FROM ROLE_PERMISSIONS;
DELETE FROM ELEMENTS;
DELETE FROM SCREEN_GROUPS;
DELETE FROM SCREENS;
DELETE FROM WORKFLOW_LEVELS;
DELETE FROM USERS;
DELETE FROM REF_INDUSTRIES;
DELETE FROM REF_COMPLIANCE_DOCS;
DELETE FROM REF_FUND_TYPES;

-- ----------------------------------------------------------------------------
-- 1. Users & Roles
-- ----------------------------------------------------------------------------
INSERT INTO USERS (user_id, user_name, role_name) VALUES
  ('alice', 'Alice (Editor)', 'Editor'),
  ('bob', 'Bob (L1 Approver)', 'Approver_L1'),
  ('carol', 'Carol (L2 Approver)', 'Approver_L2'),
  ('david', 'David (Viewer)', 'Viewer'),
  ('admin', 'Admin User', 'Admin');

-- ----------------------------------------------------------------------------
-- 2. Workflow Configuration
-- ----------------------------------------------------------------------------
INSERT INTO WORKFLOW_LEVELS (workflow_id, level_num, role_name) VALUES
  ('VENDOR_WF', 1, 'Approver_L1'),
  ('VENDOR_WF', 2, 'Approver_L2'),
  ('FUND_WF', 1, 'Approver_L1');

-- ----------------------------------------------------------------------------
-- 3. Reference Data
-- ----------------------------------------------------------------------------
INSERT INTO REF_INDUSTRIES (industry_id, industry_name) VALUES ('IT', 'IT'), ('FIN', 'Finance'), ('PHM', 'Pharma');
INSERT INTO REF_COMPLIANCE_DOCS (doc_id, doc_name) VALUES ('SOC2', 'SOC2'), ('ISO27001', 'ISO27001'), ('GDPR', 'GDPR');
INSERT INTO REF_FUND_TYPES (fund_type_id, fund_type_name) VALUES ('HF', 'Hedge Fund'), ('MF', 'Mutual Fund'), ('ETF', 'Exchange-Traded Fund'), ('PE', 'Private Equity');

-- ----------------------------------------------------------------------------
-- 4. Screen Configuration: "Vendor Onboarding" (Multi-Table)
-- ----------------------------------------------------------------------------
INSERT INTO SCREENS (screen_id, screen_name, description, target_table, unique_key_column) VALUES
  ('vendor_onboarding', 'Vendor Onboarding', 'Screen to manage new vendor information.', 'VENDOR_DATA', 'record_id');

INSERT INTO SCREEN_GROUPS (group_id, screen_id, group_name, display_order) VALUES
  ('vg_general', 'vendor_onboarding', 'General Information', 1),
  ('vg_financials', 'vendor_onboarding', 'Financials', 2),
  ('vg_compliance', 'vendor_onboarding', 'Compliance Details', 3),
  ('vg_actions', 'vendor_onboarding', 'Workflow Actions', 4);

-- Elements for Vendor Onboarding, now including a multi-table group
INSERT INTO ELEMENTS (element_id, group_id, element_type, label, db_column, display_order, target_table, options_source_table, options_value_column, options_label_column, options_query) VALUES
  -- General Group (writes to VENDOR_DATA)
  ('ve_vendor_name', 'vg_general', 'text', 'Vendor Name', 'vendor_name', 1, NULL, NULL, NULL, NULL, NULL),
  ('ve_reg_date', 'vg_general', 'date', 'Registration Date', 'registration_date', 2, NULL, NULL, NULL, NULL, NULL),
  -- Financials Group (writes to VENDOR_FINANCIALS)
  ('ve_revenue', 'vg_financials', 'number', 'Annual Revenue (USD)', 'annual_revenue', 1, 'VENDOR_FINANCIALS', NULL, NULL, NULL, NULL),
  ('ve_employees', 'vg_financials', 'number', 'Employee Count', 'employee_count', 2, 'VENDOR_FINANCIALS', NULL, NULL, NULL, NULL),
  -- Compliance Group (writes to VENDOR_DATA)
  ('ve_industry', 'vg_compliance', 'dropdown', 'Industry', 'industry', 1, NULL, 'REF_INDUSTRIES', 'INDUSTRY_ID', 'INDUSTRY_NAME', NULL),
  ('ve_docs', 'vg_compliance', 'multiselect', 'Compliance Documents', 'compliance_docs', 2, NULL, 'REF_COMPLIANCE_DOCS', 'DOC_ID', 'DOC_NAME', NULL),
  -- Actions
  ('vb_save', 'vg_actions', 'button', 'Save Draft', NULL, 1, NULL, NULL, NULL, NULL, NULL),
  ('vb_submit', 'vg_actions', 'button', 'Submit for Approval', NULL, 2, NULL, NULL, NULL, NULL),
  ('vb_approve', 'vg_actions', 'button', 'Approve', NULL, 3, NULL, NULL, NULL, NULL),
  ('vb_reject', 'vg_actions', 'button', 'Reject', NULL, 4, NULL, NULL, NULL, NULL);

-- Permissions for Vendor Onboarding, including new elements
INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write)
SELECT UUID_STRING(), element_id, role, can_read, can_write FROM (
    SELECT 've_vendor_name', 'Editor', TRUE, TRUE UNION ALL SELECT 've_vendor_name', 'Approver_L1', TRUE, FALSE UNION ALL
    SELECT 've_reg_date', 'Editor', TRUE, TRUE UNION ALL SELECT 've_reg_date', 'Approver_L1', TRUE, FALSE UNION ALL
    SELECT 've_revenue', 'Editor', TRUE, TRUE UNION ALL SELECT 've_revenue', 'Approver_L1', TRUE, FALSE UNION ALL
    SELECT 've_employees', 'Editor', TRUE, TRUE UNION ALL SELECT 've_employees', 'Approver_L1', TRUE, FALSE UNION ALL
    SELECT 've_industry', 'Editor', TRUE, TRUE UNION ALL SELECT 've_industry', 'Approver_L1', TRUE, FALSE UNION ALL
    SELECT 've_docs', 'Editor', TRUE, TRUE UNION ALL SELECT 've_docs', 'Approver_L1', TRUE, FALSE UNION ALL
    SELECT 'vb_save', 'Editor', TRUE, FALSE UNION ALL SELECT 'vb_submit', 'Editor', TRUE, FALSE UNION ALL
    SELECT 'vb_approve', 'Approver_L1', TRUE, FALSE UNION ALL SELECT 'vb_approve', 'Approver_L2', TRUE, FALSE UNION ALL
    SELECT 'vb_reject', 'Approver_L1', TRUE, FALSE UNION ALL SELECT 'vb_reject', 'Approver_L2', TRUE, FALSE
);
INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write)
SELECT UUID_STRING(), element_id, 'Admin', TRUE, TRUE FROM ELEMENTS WHERE screen_id = 'vendor_onboarding';

-- ----------------------------------------------------------------------------
-- (Other screen configurations remain the same)
-- ----------------------------------------------------------------------------
INSERT INTO SCREENS (screen_id, screen_name, description, target_table, unique_key_column) VALUES
  ('fund_screen', 'Investment Fund', 'Screen to manage investment funds.', 'FUND_DATA', 'record_id');
INSERT INTO SCREEN_GROUPS (group_id, screen_id, group_name, display_order) VALUES
  ('fg_details', 'fund_screen', 'Fund Details', 1), ('fg_actions', 'fund_screen', 'Workflow Actions', 2);
INSERT INTO ELEMENTS (element_id, group_id, element_type, label, db_column, display_order, target_table, options_source_table, options_value_column, options_label_column, options_query) VALUES
  ('fe_fund_name', 'fg_details', 'text', 'Fund Name', 'fund_name', 1, NULL, NULL, NULL, NULL, NULL),
  ('fe_inception_date', 'fg_details', 'date', 'Inception Date', 'inception_date', 2, NULL, NULL, NULL, NULL),
  ('fe_fund_type', 'fg_details', 'dropdown', 'Fund Type', 'fund_type', 3, NULL, 'REF_FUND_TYPES', 'FUND_TYPE_ID', 'FUND_TYPE_NAME', NULL),
  ('fb_save', 'fg_actions', 'button', 'Save Draft', NULL, 1, NULL, NULL, NULL, NULL),
  ('fb_submit', 'fg_actions', 'button', 'Submit for Approval', NULL, 2, NULL, NULL, NULL, NULL),
  ('fb_approve', 'fg_actions', 'button', 'Approve', NULL, 3, NULL, NULL, NULL, NULL),
  ('fb_reject', 'fg_actions', 'button', 'Reject', NULL, 4, NULL, NULL, NULL, NULL);
INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write)
SELECT UUID_STRING(), element_id, role, can_read, can_write FROM (
    SELECT 'fe_fund_name', 'Editor', TRUE, TRUE UNION ALL SELECT 'fe_inception_date', 'Editor', TRUE, TRUE UNION ALL SELECT 'fe_fund_type', 'Editor', TRUE, TRUE UNION ALL
    SELECT 'fb_save', 'Editor', TRUE, FALSE UNION ALL SELECT 'fb_submit', 'Editor', TRUE, FALSE UNION ALL
    SELECT 'fb_approve', 'Approver_L1', TRUE, FALSE UNION ALL SELECT 'fb_reject', 'Approver_L1', TRUE, FALSE
);
INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write)
SELECT UUID_STRING(), element_id, 'Admin', TRUE, TRUE FROM ELEMENTS WHERE screen_id = 'fund_screen';
INSERT INTO SCREENS (screen_id, screen_name, description, target_table, unique_key_column) VALUES
  ('admin_users', 'User Management', 'Admin screen to manage users and roles.', 'USERS', 'user_id');
INSERT INTO SCREEN_GROUPS (group_id, screen_id, group_name, display_order) VALUES
  ('ug_details', 'admin_users', 'User Details', 1);
INSERT INTO ELEMENTS (element_id, group_id, element_type, label, db_column, display_order, target_table, options_source_table, options_value_column, options_label_column, options_query) VALUES
  ('ue_user_id', 'ug_details', 'text', 'User ID', 'user_id', 1, NULL, NULL, NULL, NULL, NULL),
  ('ue_user_name', 'ug_details', 'text', 'User Name', 'user_name', 2, NULL, NULL, NULL, NULL),
  ('ue_role_name', 'ug_details', 'dropdown', 'Role', 'role_name', 3, NULL, 'USERS', 'ROLE_NAME', 'ROLE_NAME', NULL),
  ('ub_save', 'ug_details', 'button', 'Save User', NULL, 4, NULL, NULL, NULL, NULL);
INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write)
SELECT UUID_STRING(), element_id, 'Admin', TRUE, TRUE FROM ELEMENTS WHERE screen_id = 'admin_users';
