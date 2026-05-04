#!/usr/bin/env python3

import cx_Oracle
import logging
import pandas as pd
from datetime import datetime, timedelta
from .utils import sanitize_sql_identifier, get_table_row_count_estimate

class OracleConnector:
    """Oracle database connector with connection pooling"""
    
    def __init__(self, p_config):
        self.v_logger = logging.getLogger('db_sync.oracle')
        self.v_config = p_config
        self.v_connection = None
        self.v_cursor = None
        
        # Connection parameters
        self.v_host = p_config.get('oracle_source', 'v_host')
        self.v_port = p_config.getint('oracle_source', 'v_port')
        self.v_service_name = p_config.get('oracle_source', 'v_service_name')
        self.v_username = p_config.get('oracle_source', 'v_username')
        self.v_password = p_config.get('oracle_source', 'v_password')
        self.v_encoding = p_config.get('oracle_source', 'v_encoding', fallback='UTF-8')
        
        # Build connection string
        self.v_dsn = cx_Oracle.makedsn(
            host=self.v_host,
            port=self.v_port,
            service_name=self.v_service_name
        )
        
        self.v_logger.info(f"Oracle connector initialized for {self.v_host}:{self.v_port}/{self.v_service_name}")
    
    def connect(self):
        """Establish connection to Oracle database"""
        try:
            self.v_connection = cx_Oracle.connect(
                user=self.v_username,
                password=self.v_password,
                dsn=self.v_dsn,
                encoding=self.v_encoding
            )
            
            self.v_cursor = self.v_connection.cursor()
            
            # Set session parameters for better performance
            self.v_cursor.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'")
            self.v_cursor.execute("ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF'")
            
            self.v_logger.info("Successfully connected to Oracle database")
            return True
            
        except cx_Oracle.Error as v_error:
            self.v_logger.error(f"Failed to connect to Oracle: {v_error}")
            return False
    
    def disconnect(self):
        """Close Oracle database connection"""
        try:
            if self.v_cursor:
                self.v_cursor.close()
                self.v_cursor = None
            
            if self.v_connection:
                self.v_connection.close()
                self.v_connection = None
            
            self.v_logger.info("Oracle connection closed")
            
        except cx_Oracle.Error as v_error:
            self.v_logger.error(f"Error closing Oracle connection: {v_error}")
    
    def test_connection(self):
        """Test Oracle database connection"""
        try:
            if not self.v_connection:
                if not self.connect():
                    return False
            
            self.v_cursor.execute("SELECT 1 FROM DUAL")
            v_result = self.v_cursor.fetchone()
            
            if v_result and v_result[0] == 1:
                self.v_logger.info("Oracle connection test successful")
                return True
            else:
                self.v_logger.error("Oracle connection test failed")
                return False
                
        except cx_Oracle.Error as v_error:
            self.v_logger.error(f"Oracle connection test error: {v_error}")
            return False
    
    def get_table_data(self, p_table_config, p_last_sync_time=None):
        """Get data from Oracle table based on configuration"""
        try:
            v_table_name = sanitize_sql_identifier(p_table_config['v_oracle_table'])
            v_sync_mode = p_table_config['v_sync_mode']
            v_timestamp_column = p_table_config.get('v_timestamp_column')
            v_filters = p_table_config.get('v_filters', '')
            v_order_by = p_table_config.get('v_order_by', '')
            
            # Build SELECT clause with column mapping
            v_columns = []
            for v_oracle_col, v_postgres_col in p_table_config['v_column_mapping'].items():
                v_oracle_col_clean = sanitize_sql_identifier(v_oracle_col)
                v_columns.append(f"{v_oracle_col_clean} AS {v_postgres_col}")
            
            v_select_clause = ", ".join(v_columns)
            
            # Build WHERE clause
            v_where_conditions = []
            
            # Add custom filters
            if v_filters:
                # Remove WHERE keyword if present
                v_clean_filters = v_filters.replace('WHERE', '').strip()
                if v_clean_filters:
                    v_where_conditions.append(f"({v_clean_filters})")
            
            # Add incremental sync condition
            if v_sync_mode == 'incremental' and v_timestamp_column and p_last_sync_time:
                v_timestamp_col_clean = sanitize_sql_identifier(v_timestamp_column)
                v_where_conditions.append(f"{v_timestamp_col_clean} > TO_TIMESTAMP('{p_last_sync_time}', 'YYYY-MM-DD HH24:MI:SS')")
            
            # Build final SQL
            v_sql = f"SELECT {v_select_clause} FROM {v_table_name}"
            
            if v_where_conditions:
                v_sql += " WHERE " + " AND ".join(v_where_conditions)
            
            if v_order_by:
                v_order_by_clean = sanitize_sql_identifier(v_order_by)
                v_sql += f" ORDER BY {v_order_by_clean}"
            
            self.v_logger.info(f"Executing Oracle query: {v_sql}")
            
            # Execute query and return as DataFrame
            v_df = pd.read_sql(v_sql, self.v_connection)
            
            v_row_count = len(v_df)
            self.v_logger.info(f"Retrieved {v_row_count} rows from Oracle table {v_table_name}")
            
            return v_df
            
        except (cx_Oracle.Error, pd.errors.DatabaseError) as v_error:
            self.v_logger.error(f"Error retrieving data from Oracle table {p_table_config['v_oracle_table']}: {v_error}")
            raise
    
    def get_table_info(self, p_table_name):
        """Get table information from Oracle"""
        try:
            v_table_name_clean = sanitize_sql_identifier(p_table_name)
            
            # Get table schema info
            v_sql = """
            SELECT 
                column_name,
                data_type,
                data_length,
                data_precision,
                data_scale,
                nullable
            FROM user_tab_columns 
            WHERE table_name = UPPER(:table_name)
            ORDER BY column_id
            """
            
            v_schema_name, v_table_only = v_table_name_clean.split('.') if '.' in v_table_name_clean else (None, v_table_name_clean)
            
            self.v_cursor.execute(v_sql, {'table_name': v_table_only.upper()})
            v_columns = self.v_cursor.fetchall()
            
            # Get row count estimate
            v_row_count = get_table_row_count_estimate(self.v_cursor, v_table_name_clean)
            
            v_table_info = {
                'v_table_name': v_table_name_clean,
                'v_row_count': v_row_count,
                'v_columns': []
            }
            
            for v_col in v_columns:
                v_column_info = {
                    'v_column_name': v_col[0],
                    'v_data_type': v_col[1],
                    'v_data_length': v_col[2],
                    'v_data_precision': v_col[3],
                    'v_data_scale': v_col[4],
                    'v_nullable': v_col[5] == 'Y'
                }
                v_table_info['v_columns'].append(v_column_info)
            
            self.v_logger.info(f"Retrieved table info for {v_table_name_clean}: {len(v_columns)} columns, ~{v_row_count} rows")
            
            return v_table_info
            
        except cx_Oracle.Error as v_error:
            self.v_logger.error(f"Error getting table info for {p_table_name}: {v_error}")
            raise
    
    def get_max_timestamp(self, p_table_name, p_timestamp_column):
        """Get maximum timestamp value from Oracle table"""
        try:
            v_table_name_clean = sanitize_sql_identifier(p_table_name)
            v_timestamp_col_clean = sanitize_sql_identifier(p_timestamp_column)
            
            v_sql = f"""
            SELECT MAX({v_timestamp_col_clean}) 
            FROM {v_table_name_clean}
            """
            
            self.v_cursor.execute(v_sql)
            v_result = self.v_cursor.fetchone()
            
            if v_result and v_result[0]:
                v_max_timestamp = v_result[0]
                if isinstance(v_max_timestamp, datetime):
                    return v_max_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    return str(v_max_timestamp)
            
            return None
            
        except cx_Oracle.Error as v_error:
            self.v_logger.error(f"Error getting max timestamp from {p_table_name}.{p_timestamp_column}: {v_error}")
            raise
    
    def validate_table_exists(self, p_table_name):
        """Validate if table exists in Oracle"""
        try:
            v_table_name_clean = sanitize_sql_identifier(p_table_name)
            v_schema_name, v_table_only = v_table_name_clean.split('.') if '.' in v_table_name_clean else (None, v_table_name_clean)
            
            v_sql = """
            SELECT COUNT(*) 
            FROM user_tables 
            WHERE table_name = UPPER(:table_name)
            """
            
            self.v_cursor.execute(v_sql, {'table_name': v_table_only})
            v_count = self.v_cursor.fetchone()[0]
            
            v_exists = v_count > 0
            self.v_logger.info(f"Oracle table {v_table_name_clean} exists: {v_exists}")
            
            return v_exists
            
        except cx_Oracle.Error as v_error:
            self.v_logger.error(f"Error validating Oracle table {p_table_name}: {v_error}")
            return False
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()