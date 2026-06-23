import pytest

def test_database_connection_and_dummy_table(db_connection):

    dummy_table_name = "test_dummy_pipeline_table"
    test_id = 999
    test_name = "Enterprise_Test_Row"

    with db_connection.cursor() as cursor:
        try:
            # Create a dummy table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {dummy_table_name} (
                    id INT PRIMARY KEY,
                    name VARCHAR(50)
                );
            """)

            # Insert a test record
            cursor.execute(
                f"INSERT INTO {dummy_table_name} (id, name) VALUES (%s, %s);",
                (test_id, test_name)
            )

            # Read the record back
            cursor.execute(f"SELECT id, name FROM {dummy_table_name} WHERE id = %s;", (test_id,))
            result = cursor.fetchone()

            assert result is not None, "Failed to retrieve the inserted record."
            assert result[0] == test_id
            assert result[1] == test_name

        finally:
            # Cleanup: Destroy the evidence regardless of pass/fail
            cursor.execute(f"DROP TABLE IF EXISTS {dummy_table_name};")
            db_connection.commit()