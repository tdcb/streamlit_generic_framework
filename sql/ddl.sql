-- Streamlit Dynamic UI Framework for Snowflake
-- v5: Multi-Table Support

-- ----------------------------------------------------------------------------
-- Configuration Tables
-- ----------------------------------------------------------------------------

CREATE OR REPLACE TABLE SCREENS (
  screen_id VARCHAR PRIMARY KEY,
  screen_name VARCHAR NOT NULL,
  description VARCHAR,
  target_table VARCHAR NOT NULL, -- This is the PRIMARY entity table for the screen
  unique_key_column VARCHAR NOT NULL
);

CREATE OR REPLACE TABLE SCREEN_GROUPS (
  group_id VARCHAR PRIMARY KEY,
  screen_id VARCHAR NOT NULL REFERENCES SCREENS(screen_id),
  group_name VARCHAR NOT NULL,
  display_order INT
);

-- Updated ELEMENTS table for multi-table support
CREATE OR REPLACE TABLE ELEMENTS (
  element_id VARCHAR PRIMARY KEY,
  group_id VARCHAR NOT NULL REFERENCES SCREEN_GROUPS(group_id),
  element_type VARCHAR NOT NULL,
  label VARCHAR NOT NULL,
  db_column VARCHAR,
  display_order INT,
  target_table VARCHAR, -- If NULL, defaults to screen's primary table. Otherwise, specifies a secondary table.
  options_source_table VARCHAR,
  options_value_column VARCHAR,
  options_label_column VARCHAR,
  options_query VARCHAR
);

CREATE OR REPLACE TABLE ROLE_PERMISSIONS (
  permission_id VARCHAR PRIMARY KEY,
  element_id VARCHAR NOT NULL REFERENCES ELEMENTS(element_id),
  role_name VARCHAR NOT NULL,
  can_read BOOLEAN,
  can_write BOOLEAN
);

CREATE OR REPLACE TABLE WORKFLOW_LEVELS (
  workflow_id VARCHAR,
  level_num INT,
  role_name VARCHAR NOT NULL,
  PRIMARY KEY (workflow_id, level_num)
);

CREATE OR REPLACE TABLE USERS (
  user_id VARCHAR PRIMARY KEY,
  user_name VARCHAR NOT NULL,
  role_name VARCHAR NOT NULL
);

-- ----------------------------------------------------------------------------
-- Reference Data Tables
-- ----------------------------------------------------------------------------

CREATE OR REPLACE TABLE REF_INDUSTRIES ( industry_id VARCHAR PRIMARY KEY, industry_name VARCHAR NOT NULL );
CREATE OR REPLACE TABLE REF_COMPLIANCE_DOCS ( doc_id VARCHAR PRIMARY KEY, doc_name VARCHAR NOT NULL );
CREATE OR REPLACE TABLE REF_FUND_TYPES ( fund_type_id VARCHAR PRIMARY KEY, fund_type_name VARCHAR NOT NULL );

-- ----------------------------------------------------------------------------
-- Data & Audit Tables
-- ----------------------------------------------------------------------------

-- Primary entity table for "Vendor Onboarding" screen (Versioned)
CREATE OR REPLACE TABLE VENDOR_DATA (
  record_id VARCHAR,
  version INT,
  vendor_name VARCHAR,
  registration_date DATE,
  industry VARCHAR,
  compliance_docs VARCHAR,
  status VARCHAR,
  current_approver_level INT,
  created_by VARCHAR,
  created_at TIMESTAMP_LTZ,
  last_updated_by VARCHAR,
  last_updated_at TIMESTAMP_LTZ,
  PRIMARY KEY (record_id, version)
);

-- New SECONDARY entity table for "Vendor Onboarding" screen (Not Versioned)
CREATE OR REPLACE TABLE VENDOR_FINANCIALS (
  record_id VARCHAR PRIMARY KEY, -- Foreign key to VENDOR_DATA
  annual_revenue NUMBER,
  employee_count NUMBER,
  last_updated_by VARCHAR,
  last_updated_at TIMESTAMP_LTZ
);

-- Entity table for "Investment Fund" screen
CREATE OR REPLACE TABLE FUND_DATA (
  record_id VARCHAR,
  version INT,
  fund_name VARCHAR,
  inception_date DATE,
  fund_type VARCHAR,
  status VARCHAR,
  current_approver_level INT,
  created_by VARCHAR,
  created_at TIMESTAMP_LTZ,
  last_updated_by VARCHAR,
  last_updated_at TIMESTAMP_LTZ,
  PRIMARY KEY (record_id, version)
);

-- Tracks all changes to data and workflow status for a complete audit trail.
CREATE OR REPLACE TABLE AUDIT_LOG (
  audit_id VARCHAR PRIMARY KEY,
  record_id VARCHAR,
  table_name VARCHAR,
  column_name VARCHAR,
  old_value VARCHAR,
  new_value VARCHAR,
  action_type VARCHAR,
  action_timestamp TIMESTAMP_LTZ,
  user_id VARCHAR,
  user_role VARCHAR,
  record_version INT,
  comments VARCHAR
);
