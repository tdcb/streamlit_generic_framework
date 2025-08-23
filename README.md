# Streamlit Dynamic UI Framework for Snowflake

This project provides a configurable, framework-based approach to building data-centric applications that run **natively inside Snowflake** as a Streamlit in Snowflake (SiS) app.

The core principle is **configuration over code**. New screens, UI elements, user roles, and workflows can be defined by adding or updating records in Snowflake tables, without changing the Python source code.

## Key Features

- **Native Snowflake Integration**: Runs directly within the Snowflake ecosystem, leveraging Snowpark and Snowflake's authentication.
- **Dynamic UI Rendering**: Define screens, groups, and UI elements (text, number, date, dropdowns, etc.) in database tables.
- **Role-Based Access Control (RBAC)**: Utilizes Snowflake's roles to control read/write access for each UI element.
- **Configurable Workflows**: Define multi-level approval workflows.
- **Full Audit & History**: Every data change and workflow action is tracked in an audit log. Data is versioned, providing a complete history of edits.
- **Self-Configuration**: An Admin UI is provided to manage users and other configurations directly from the application itself.

## Deployment to Snowflake

Follow these steps to deploy and run the application within your Snowflake account.

### 1. Database and Role Setup

You will need a Snowflake account with privileges to create databases, stages, and roles.

1.  **Create Tables**: Connect to your Snowflake account (e.g., via a Snowsight worksheet) and run the DDL script to create all the necessary tables.
    ```sql
    -- Run the content of sql/ddl.sql
    ```

2.  **Seed Data**: Run the data script to populate the tables with the initial configuration for the "Vendor Onboarding" example and the Admin UI.
    ```sql
    -- Run the content of sql/data.sql
    ```

3.  **Create and Assign Roles**: The application's permissions are mapped to Snowflake roles. You must create these roles in Snowflake and grant them to the users who will be using the app. The sample data uses the roles `Admin`, `Editor`, `Approver_L1`, `Approver_L2`, and `Viewer`.

    ```sql
    -- Execute these commands as a user with role creation privileges (e.g., ACCOUNTADMIN or SECURITYADMIN)
    USE ROLE SECURITYADMIN;
    CREATE ROLE IF NOT EXISTS Admin;
    CREATE ROLE IF NOT EXISTS Editor;
    CREATE ROLE IF NOT EXISTS Approver_L1;
    CREATE ROLE IF NOT EXISTS Approver_L2;
    CREATE ROLE IF NOT EXISTS Viewer;

    -- Grant roles to your app's parent role (e.g., SYSADMIN)
    GRANT ROLE Admin TO ROLE SYSADMIN;
    GRANT ROLE Editor TO ROLE SYSADMIN;
    GRANT ROLE Approver_L1 TO ROLE SYSADMIN;
    GRANT ROLE Approver_L2 TO ROLE SYSADMIN;
    GRANT ROLE Viewer TO ROLE SYSADMIN;

    -- Grant roles to specific users
    -- Example: GRANT ROLE Editor TO USER "ALICE";
    ```
    **Note:** Ensure the users in the `USERS` table exist as actual Snowflake users. The app authenticates using the logged-in Snowflake user's name.

### 2. Upload Application Files

1.  **Create a Stage**: Create a named stage where you will upload the application files.
    ```sql
    CREATE OR REPLACE STAGE dynamic_ui_stage;
    ```

2.  **Upload Files**: Upload `src/app.py` and `environment.yml` to this stage. You can do this using the Snowsight UI or the SnowSQL CLI.

    Using SnowSQL:
    ```sql
    -- from your local machine's terminal, after configuring SnowSQL
    -- Make sure your current directory is the project root.
    snowsql -q "PUT file://src/app.py @dynamic_ui_stage OVERWRITE=TRUE AUTO_COMPRESS=FALSE"
    snowsql -q "PUT file://environment.yml @dynamic_ui_stage OVERWRITE=TRUE AUTO_COMPRESS=FALSE"
    ```

### 3. Create the Streamlit Application

Create the `STREAMLIT` object in Snowflake, referencing the stage and the main application file.

```sql
CREATE OR REPLACE STREAMLIT dynamic_ui_app
  ROOT_LOCATION = '@dynamic_ui_stage'
  MAIN_FILE = '/app.py'
  QUERY_WAREHOUSE = 'YOUR_COMPUTE_WH'; -- Specify the warehouse to use
```
*Replace `YOUR_COMPUTE_WH` with the name of the warehouse the app should run on.*

## Running the Application

Once deployed, you can run the app by:
1.  Navigating to the "Streamlit" section in the Snowflake UI (Snowsight).
2.  Finding and clicking on your app, named `DYNAMIC_UI_APP`.
3.  The app will launch, automatically authenticating you as your current Snowflake user.

To learn more about configuring screens and workflows, see the [Configuration Guide](./docs/configuration.md).
