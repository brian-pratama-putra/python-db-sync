#!/usr/bin/env python3

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import json

class NotificationSender:
    """Email notification sender for sync results"""
    
    def __init__(self, p_config):
        self.v_logger = logging.getLogger('db_sync.notification')
        self.v_config = p_config
        
        # Email configuration
        self.v_smtp_server = p_config.get('email_notification', 'v_smtp_server')
        self.v_smtp_port = p_config.getint('email_notification', 'v_smtp_port')
        self.v_email_from = p_config.get('email_notification', 'v_email_from')
        self.v_email_to = p_config.get('email_notification', 'v_email_to').split(',')
        self.v_email_password = p_config.get('email_notification', 'v_email_password')
        self.v_send_success_email = p_config.getboolean('email_notification', 'v_send_success_email', fallback=False)
        self.v_send_error_email = p_config.getboolean('email_notification', 'v_send_error_email', fallback=True)
        
        self.v_logger.info(f"Notification sender initialized for {len(self.v_email_to)} recipients")
    
    def send_sync_report(self, p_sync_results, p_sync_type='incremental'):
        """Send sync report via email"""
        try:
            # Determine if we should send email
            v_has_errors = any(not result.get('v_success', True) for result in p_sync_results)
            
            if v_has_errors and not self.v_send_error_email:
                self.v_logger.info("Errors found but error email disabled")
                return True
            
            if not v_has_errors and not self.v_send_success_email:
                self.v_logger.info("Sync successful but success email disabled")
                return True
            
            # Generate email content
            v_subject = self._generate_email_subject(p_sync_results, p_sync_type, v_has_errors)
            v_html_body = self._generate_html_report(p_sync_results, p_sync_type, v_has_errors)
            
            # Send email
            return self._send_email(v_subject, v_html_body)
            
        except Exception as v_error:
            self.v_logger.error(f"Error sending sync report: {v_error}")
            return False
    
    def send_error_alert(self, p_error_message, p_table_name=None):
        """Send immediate error alert"""
        try:
            v_subject = f"🚨 Database Sync Error Alert"
            if p_table_name:
                v_subject += f" - {p_table_name}"
            
            v_html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 5px;">
                    <h2 style="color: #721c24; margin-top: 0;">Database Sync Error</h2>
                    <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    {f'<p><strong>Table:</strong> {p_table_name}</p>' if p_table_name else ''}
                    <p><strong>Error:</strong></p>
                    <pre style="background-color: #f1f1f1; padding: 10px; border-radius: 3px; overflow-x: auto;">{p_error_message}</pre>
                </div>
                
                <p style="margin-top: 20px; color: #666;">
                    This is an automated alert from the Database Sync System.
                </p>
            </body>
            </html>
            """
            
            return self._send_email(v_subject, v_html_body)
            
        except Exception as v_error:
            self.v_logger.error(f"Error sending error alert: {v_error}")
            return False
    
    def _generate_email_subject(self, p_sync_results, p_sync_type, p_has_errors):
        """Generate email subject based on sync results"""
        v_total_tables = len(p_sync_results)
        v_success_count = sum(1 for result in p_sync_results if result.get('v_success', True))
        v_error_count = v_total_tables - v_success_count
        
        if p_has_errors:
            v_status_icon = "🚨"
            v_status_text = f"FAILED ({v_error_count}/{v_total_tables} errors)"
        else:
            v_status_icon = "✅"
            v_status_text = f"SUCCESS ({v_success_count}/{v_total_tables} tables)"
        
        return f"{v_status_icon} DB Sync {p_sync_type.title()} - {v_status_text}"
    
    def _generate_html_report(self, p_sync_results, p_sync_type, p_has_errors):
        """Generate HTML email report"""
        v_total_rows = sum(result.get('v_rows_processed', 0) for result in p_sync_results)
        v_total_duration = sum(result.get('v_duration_seconds', 0) for result in p_sync_results)
        
        # Summary statistics
        v_success_count = sum(1 for result in p_sync_results if result.get('v_success', True))
        v_error_count = len(p_sync_results) - v_success_count
        
        # Generate table rows
        v_table_rows = ""
        for v_result in p_sync_results:
            v_status_icon = "✅" if v_result.get('v_success', True) else "❌"
            v_status_class = "success" if v_result.get('v_success', True) else "error"
            
            v_table_rows += f"""
            <tr class="{v_status_class}">
                <td>{v_status_icon}</td>
                <td>{v_result.get('v_table_name', 'Unknown')}</td>
                <td>{v_result.get('v_sync_mode', 'Unknown')}</td>
                <td>{v_result.get('v_rows_processed', 0):,}</td>
                <td>{v_result.get('v_duration_seconds', 0):.2f}s</td>
                <td>{v_result.get('v_error_message', 'Success') if not v_result.get('v_success', True) else 'Success'}</td>
            </tr>
            """
        
        v_html_template = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background-color: {'#dc3545' if p_has_errors else '#28a745'}; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px; }}
                .summary-box {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; }}
                .summary-box h3 {{ margin: 0; font-size: 24px; color: #495057; }}
                .summary-box p {{ margin: 5px 0 0 0; color: #6c757d; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #343a40; color: white; }}
                .success {{ background-color: #d4edda; }}
                .error {{ background-color: #f8d7da; }}
                .footer {{ text-align: center; color: #6c757d; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Database Sync Report</h1>
                    <p><strong>Sync Type:</strong> {p_sync_type.title()} | <strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>

                <div class="summary">
                    <div class="summary-box">
                        <h3>{len(p_sync_results)}</h3>
                        <p>Total Tables</p>
                    </div>
                    <div class="summary-box">
                        <h3>{v_success_count}</h3>
                        <p>Successful</p>
                    </div>
                    <div class="summary-box">
                        <h3>{v_error_count}</h3>
                        <p>Failed</p>
                    </div>
                    <div class="summary-box">
                        <h3>{v_total_rows:,}</h3>
                        <p>Rows Processed</p>
                    </div>
                    <div class="summary-box">
                        <h3>{v_total_duration:.1f}s</h3>
                        <p>Total Duration</p>
                    </div>
                </div>

                <h3>📋 Sync Details</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Table Name</th>
                            <th>Sync Mode</th>
                            <th>Rows Processed</th>
                            <th>Duration</th>
                            <th>Message</th>
                        </tr>
                    </thead>
                    <tbody>
                        {v_table_rows}
                    </tbody>
                </table>

                <div class="footer">
                    <p>Generated by Database Sync System | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>This is an automated report from Oracle → PostgreSQL synchronization</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return v_html_template
    
    def _send_email(self, p_subject, p_html_body):
        """Send email using SMTP"""
        try:
            # Create message
            v_msg = MIMEMultipart('alternative')
            v_msg['Subject'] = p_subject
            v_msg['From'] = self.v_email_from
            v_msg['To'] = ', '.join(self.v_email_to)
            
            # Attach HTML body
            v_html_part = MIMEText(p_html_body, 'html', 'utf-8')
            v_msg.attach(v_html_part)
            
            # Send email
            with smtplib.SMTP(self.v_smtp_server, self.v_smtp_port) as v_server:
                v_server.starttls()
                v_server.login(self.v_email_from, self.v_email_password)
                v_server.send_message(v_msg)
            
            self.v_logger.info(f"Email sent successfully to {len(self.v_email_to)} recipients")
            return True
            
        except smtplib.SMTPException as v_error:
            self.v_logger.error(f"SMTP error sending email: {v_error}")
            return False
        except Exception as v_error:
            self.v_logger.error(f"Error sending email: {v_error}")
            return False
    
    def test_email_connection(self):
        """Test email connection and send test message"""
        try:
            v_test_subject = "🧪 Database Sync - Test Email"
            v_test_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h2>Database Sync Test Email</h2>
                <p>This is a test email from the Database Sync System.</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>SMTP Server:</strong> {self.v_smtp_server}:{self.v_smtp_port}</p>
                <p>If you receive this email, the email configuration is working correctly.</p>
            </body>
            </html>
            """
            
            return self._send_email(v_test_subject, v_test_body)
            
        except Exception as v_error:
            self.v_logger.error(f"Error testing email connection: {v_error}")
            return False