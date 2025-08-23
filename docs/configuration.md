# Configuration Guide

The Streamlit Dynamic UI Framework is configured entirely by manipulating data in the Snowflake configuration tables. This guide explains the role of each table and provides step-by-step instructions for common configuration tasks.

## Core Concepts

The framework is built on a hierarchy of configuration objects:

- **Screens**: The highest-level component, representing a single page or form in the application (e.g., "Vendor Onboarding"). Each screen is linked to a `target_table` in the database where its data is stored.
- **Groups**: A screen is composed of one or more groups, which are visual sections or cards that contain UI elements (e.g., "General Information").
- **Elements**: A group contains one or more elements, which are the individual Streamlit widgets like text inputs, date selectors, dropdowns, and buttons.
- **Permissions**: Role-based access is controlled by linking roles to elements in the `ROLE_PERMISSIONS` table. You can specify `can_read` and `can_write` privileges. For buttons, `can_read` controls visibility.
- **Workflows**: An approval workflow is a sequence of roles defined in the `WORKFLOW_LEVELS` table, identified by a `workflow_id`.

## How to Add a New Screen

Let's say you want to create a new screen to manage "Products". Assume you have a `PRODUCTS` table similar to the `VENDOR_DATA` table.

### Step 1: Create the Target Table

First, ensure the data table exists in Snowflake.
```sql
CREATE OR REPLACE TABLE PRODUCTS (
  record_id VARCHAR,
  version INT,
  product_name VARCHAR,
  release_date DATE,
  category VARCHAR,
  status VARCHAR,
  current_approver_level INT,
  created_by VARCHAR,
  created_at TIMESTAMP_LTZ,
  last_updated_by VARCHAR,
  last_updated_at TIMESTAMP_LTZ,
  PRIMARY KEY (record_id, version)
);
```

### Step 2: Define the Screen

Add an entry to the `SCREENS` table.

```sql
INSERT INTO SCREENS (screen_id, screen_name, description, target_table, unique_key_column) VALUES
  ('product_screen', 'Product Management', 'Screen to manage new products.', 'PRODUCTS', 'record_id');
```

### Step 3: Define Groups

Add groups for your new screen.

```sql
INSERT INTO SCREEN_GROUPS (group_id, screen_id, group_name, display_order) VALUES
  ('pg_details', 'product_screen', 'Product Details', 1),
  ('pg_actions', 'product_screen', 'Actions', 2);
```

### Step 4: Define Elements

Add the UI elements for each group.

```sql
INSERT INTO ELEMENTS (element_id, group_id, element_type, label, db_column, options_query, display_order) VALUES
  -- Product Details
  ('pe_product_name', 'pg_details', 'text', 'Product Name', 'product_name', NULL, 1),
  ('pe_release_date', 'pg_details', 'date', 'Release Date', 'release_date', NULL, 2),
  ('pe_category', 'pg_details', 'dropdown', 'Category', 'category', 'SELECT ''Software'', ''Hardware''', 3),
  -- Action Buttons
  ('pb_save', 'pg_actions', 'button', 'Save Draft', NULL, NULL, 1),
  ('pb_submit', 'pg_actions', 'button', 'Submit for Approval', NULL, NULL, 2);
```

### Step 5: Assign Permissions

Finally, grant roles permission to see and interact with the new elements.

```sql
-- Grant 'Editor' role read/write access to data fields
INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write) VALUES
  (UUID_STRING(), 'pe_product_name', 'Editor', TRUE, TRUE),
  (UUID_STRING(), 'pe_release_date', 'Editor', TRUE, TRUE),
  (UUID_STRING(), 'pe_category', 'Editor', TRUE, TRUE);

-- Grant 'Editor' role visibility of the buttons
INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write) VALUES
  (UUID_STRING(), 'pb_save', 'Editor', TRUE, FALSE),
  (UUID_STRING(), 'pb_submit', 'Editor', TRUE, FALSE);
```
After adding these records, the "Product Management" screen will automatically appear in the UI for any user with the `Editor` role.

## How to Configure a Workflow

1.  **Define Levels**: Add entries to the `WORKFLOW_LEVELS` table. For example, to create a simple, single-level approval workflow for a manager:
    ```sql
    INSERT INTO WORKFLOW_LEVELS (workflow_id, level_num, role_name) VALUES
      ('MANAGER_WF', 1, 'Manager');
    ```

2.  **Assign to Screen**: The current application hardcodes the `'VENDOR_WF'` for the vendor screen. A future enhancement would be to add a `workflow_id` column to the `SCREENS` table to make this dynamic.

3.  **Create Approver Role**: Ensure users who need to approve have the `Manager` role (or whichever roles you defined).
    ```sql
    INSERT INTO USERS (user_id, user_name, role_name) VALUES
      ('manager_user', 'Manager User', 'Manager');
    ```

4.  **Add Buttons & Permissions**: Make sure your screen has "Approve" and "Reject" buttons and that the `Manager` role has `can_read` permission for them.
    ```sql
    INSERT INTO ELEMENTS (element_id, group_id, element_type, label, ...) VALUES
      ('pb_approve', 'pg_actions', 'button', 'Approve', ...),
      ('pb_reject', 'pg_actions', 'button', 'Reject', ...);

    INSERT INTO ROLE_PERMISSIONS (permission_id, element_id, role_name, can_read, can_write) VALUES
      (UUID_STRING(), 'pb_approve', 'Manager', TRUE, FALSE),
      (UUID_STRING(), 'pb_reject', 'Manager', TRUE, FALSE);
    ```
The application logic will automatically show these buttons to the `Manager` user when a record's status is `PENDING_L1`.
