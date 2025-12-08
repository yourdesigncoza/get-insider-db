"""Tests for the form345_loader module, focusing on the load_file function.
These tests use mocking to isolate the database interactions.
"""

import io
import csv
import pandas as pd
from unittest.mock import MagicMock, patch
from src.loaders.form345_loader import load_file
from src.config import get_engine # Needed to mock get_engine in later tests if we want to bypass dotenv

# Sample TSV content for testing
SAMPLE_TSV_CONTENT = """
ACCESSION_NUMBER	FILING_DATE	ISSUERCIK
0000000001-00-000001	2023-01-01	12345
0000000002-00-000002	2023-01-02	67890
"""

@patch('src.loaders.form345_loader.pd.read_csv')
def test_load_file_uses_copy_expert(mock_read_csv):
    """
    Verify that load_file correctly calls psycopg2's copy_expert with expected arguments.
    """
    mock_cursor = MagicMock()
    mock_dbapi_conn = MagicMock()
    mock_dbapi_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_engine_connect = MagicMock()
    mock_engine_connect.connection = mock_dbapi_conn
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_engine_connect

    # Prepare the DataFrame that pd.read_csv will return
    df_to_return = pd.DataFrame({
        'ACCESSION_NUMBER': ['0000000001-00-000001', '0000000002-00-000002'],
        'FILING_DATE': ['2023-01-01', '2023-01-02'],
        'ISSUERCIK': ['12345', '67890']
    }, dtype=str)
    mock_read_csv.return_value = df_to_return

    # Create a dummy file path object (only its name is used for logging/context)
    mock_file_path = MagicMock()
    mock_file_path.name = "dummy.tsv"

    table_name = "form345_submission"
    rows_inserted = load_file(mock_file_path, mock_engine, table=table_name)

    # Assertions
    assert rows_inserted == 2 # Based on SAMPLE_TSV_CONTENT
    
    # Verify pd.read_csv was called once with the file path (even if not used internally now)
    mock_read_csv.assert_called_once_with(mock_file_path, sep="\t", dtype=str)

    # Verify connect was called
    mock_engine.connect.assert_called_once()
    mock_dbapi_conn.cursor.assert_called_once()

    # Verify copy_expert was called
    expected_sql_prefix = f"COPY public.{table_name} (\"ACCESSION_NUMBER\",\"FILING_DATE\",\"ISSUERCIK\") FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '')"
    args, _ = mock_cursor.copy_expert.call_args
    assert args[0].strip().startswith(expected_sql_prefix.strip())
    
    # Check the buffer content passed to copy_expert
    buffer_content = args[1].read()
    expected_buffer_content = "0000000001-00-000001\t2023-01-01\t12345\n0000000002-00-000002\t2023-01-02\t67890\n"
    assert buffer_content == expected_buffer_content

    # Verify commit was called on the raw connection
    mock_dbapi_conn.commit.assert_called_once()

@patch('src.loaders.form345_loader.pd.read_csv')
def test_load_file_handles_read_error(mock_read_csv):
    """
    Verify that load_file correctly handles errors during pandas.read_csv.
    """
    mock_engine = MagicMock()
    mock_file_path = MagicMock()
    
    # Simulate an error during pandas.read_csv
    mock_read_csv.side_effect = Exception("File read error")

    try:
        load_file(mock_file_path, mock_engine, table="any_table")
        assert False, "Expected an exception to be raised"
    except Exception as e:
        assert str(e) == "File read error"
    
    # Ensure no database interaction occurred if file reading failed
    mock_engine.connect.assert_not_called()

@patch('src.loaders.form345_loader.pd.read_csv')
def test_load_file_handles_db_error(mock_read_csv):
    """
    Verify that load_file correctly handles errors during the database COPY operation.
    """
    mock_cursor = MagicMock()
    mock_dbapi_conn = MagicMock()
    mock_dbapi_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_engine_connect = MagicMock()
    mock_engine_connect.connection = mock_dbapi_conn
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_engine_connect
    
    # Ensure pd.read_csv returns a valid DataFrame for this test
    mock_read_csv.return_value = pd.DataFrame({
        'ACCESSION_NUMBER': ['0000000001-00-000001'],
        'FILING_DATE': ['2023-01-01'],
        'ISSUERCIK': ['12345']
    }, dtype=str)

    # Create a dummy file path object
    mock_file_path = MagicMock()
    mock_file_path.name = "dummy.tsv"

    # Simulate an error during copy_expert
    mock_cursor.copy_expert.side_effect = Exception("Database copy error")

    try:
        load_file(mock_file_path, mock_engine, table="any_table")
        assert False, "Expected an exception to be raised"
    except Exception as e:
        assert str(e) == "Database copy error"
    
    # Ensure commit was NOT called if copy_expert failed
    mock_dbapi_conn.commit.assert_not_called()