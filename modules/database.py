"""
Analyzer for Database files (MySQL, PostgreSQL, SQLite, etc.).
Determines if a file is part of a larger database project/dump structure or a standalone script.
Handles both SQL dump files and raw database files (.MYD, .MYI, .FRM for MySQL, etc.).
"""

import os
import re
from typing import Dict, Any, Optional, List
from modules.base import BaseAnalyzer
from models import FileInfo


class DatabaseAnalyzer(BaseAnalyzer):
    """Analyzes SQL and database dump files."""

    def __init__(self):
        self._priority = 70  # High priority to catch DB structures before generic text
        self._name = "database"
        self.sql_extensions = {'.sql', '.dump', '.pgsql', '.mysql', '.sqlite'}
        # MySQL raw database files
        self.mysql_db_extensions = {'.myd', '.myi', '.frm', '.ibd', '.opt'}
        # PostgreSQL raw database files
        self.postgres_db_extensions = {'.data', '.control'}
        # All database-related extensions
        self.db_extensions = self.sql_extensions | self.mysql_db_extensions | self.postgres_db_extensions
        
        self.db_keywords = [
            'CREATE TABLE', 'INSERT INTO', 'DROP TABLE', 'ALTER TABLE',
            'SELECT * FROM', 'UPDATE ', 'DELETE FROM', 'COMMIT', 'ROLLBACK',
            'BEGIN TRANSACTION', 'CREATE DATABASE', 'USE '
        ]
        self.mysql_specific = ['AUTO_INCREMENT', 'ENGINE=InnoDB', 'DEFAULT CHARSET=utf8', '/*!40']
        self.postgres_specific = ['SERIAL', 'TEXT[]', 'TIMESTAMPTZ', 'PL/pgSQL', '::text', 'oid']
        
        # MySQL database directory indicators
        self.mysql_db_indicators = ['db.opt', 'db.inc']
        # PostgreSQL data directory indicators  
        self.postgres_db_indicators = ['PG_VERSION', 'postgresql.conf', 'pg_hba.conf']

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def name(self) -> str:
        return self._name

    def can_handle(self, filepath: str) -> bool:
        _, ext = os.path.splitext(filepath.lower())
        if ext in self.db_extensions:
            return True
        
        # Check content for SQL signatures if extension is unknown or generic (.txt, .dat)
        if ext in ['.txt', '.dat', '.out', '']:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    sample = f.read(2048).upper()
                    if any(kw in sample for kw in self.db_keywords):
                        return True
            except Exception:
                pass
        return False

    def analyze(self, filepath: str, existing_context: dict) -> Optional[FileInfo]:
        dir_path = os.path.dirname(filepath)
        file_name = os.path.basename(filepath)
        _, ext = os.path.splitext(file_name.lower())
        
        # 1. Handle raw MySQL database files (.MYD, .MYI, .FRM, .IBD)
        if ext in self.mysql_db_extensions:
            # These are always part of a database - find the database directory
            db_root = self._find_mysql_database_root(dir_path)
            if db_root:
                return self._make_info(
                    filepath=filepath,
                    ai_category="Database",
                    ai_subcategory="MySQL Data File",
                    is_part_of_project=True,
                    project_root=db_root,
                    algorithmic_reasoning=f"MySQL database file belongs to database at {db_root}"
                )
            # Fallback: treat parent directory as the database root
            return self._make_info(
                filepath=filepath,
                ai_category="Database",
                ai_subcategory="MySQL Data File",
                is_part_of_project=True,
                project_root=dir_path,
                algorithmic_reasoning=f"MySQL database file, treating containing directory as database root"
            )
        
        # 2. Handle PostgreSQL data files
        if ext in self.postgres_db_extensions or file_name in ['PG_VERSION', 'postgresql.conf']:
            pg_root = self._find_postgresql_data_root(dir_path)
            if pg_root:
                return self._make_info(
                    filepath=filepath,
                    ai_category="Database",
                    ai_subcategory="PostgreSQL Data File",
                    is_part_of_project=True,
                    project_root=pg_root,
                    algorithmic_reasoning=f"PostgreSQL data file belongs to cluster at {pg_root}"
                )
            return self._make_info(
                filepath=filepath,
                ai_category="Database",
                ai_subcategory="PostgreSQL Data File",
                is_part_of_project=True,
                project_root=dir_path,
                algorithmic_reasoning="PostgreSQL data file, treating containing directory as data root"
            )
        
        # Read file content for SQL analysis
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            content = ""
        
        # 3. Check if there are multiple SQL files in the current directory
        sql_files_in_dir = self._get_sql_files_in_directory(dir_path)
        
        if len(sql_files_in_dir) > 1:
            # Multiple SQL files suggest a collective dump or migration set
            return self._make_info(
                filepath=filepath,
                ai_category="Database",
                ai_subcategory="Migration Set / Dump Part",
                is_part_of_project=True,
                project_root=dir_path,
                algorithmic_reasoning=f"Found {len(sql_files_in_dir)} SQL files in directory, treating as a cohesive unit."
            )
        
        # 4. Check if this file belongs to a Database Project Folder (parent directories)
        project_root = self._find_db_project_root(dir_path)
        
        if project_root:
            # It's part of a structured DB project (migrations, full dump folder, etc.)
            return self._make_info(
                filepath=filepath,
                ai_category="Database",
                ai_subcategory="Project File",
                is_part_of_project=True,
                project_root=project_root,
                algorithmic_reasoning=f"File belongs to a database project structure located at {project_root}"
            )

        # 5. Standalone SQL file - needs AI categorization
        db_type = self._detect_dialect(content)
        content_type = self._detect_content_type(content)
        
        return self._make_info(
            filepath=filepath,
            ai_category="Database",
            ai_subcategory="Standalone Script",
            is_part_of_project=False,
            project_root=None,
            algorithmic_reasoning=f"Standalone {db_type} file ({content_type}). No surrounding project structure detected."
        )

    def _find_mysql_database_root(self, start_path: str) -> Optional[str]:
        """
        Find MySQL database directory by looking for db.opt or multiple .frm/.MYD files.
        MySQL stores each database in a separate directory with db.opt and table files.
        """
        current_path = start_path
        visited = 0
        max_depth = 5
        
        while current_path and os.path.isdir(current_path) and visited < max_depth:
            # Check for MySQL database indicators
            has_db_opt = any(f in os.listdir(current_path) for f in self.mysql_db_indicators)
            frm_files = [f for f in os.listdir(current_path) if f.endswith('.frm')]
            myd_files = [f for f in os.listdir(current_path) if f.endswith('.myd')]
            
            if has_db_opt or (len(frm_files) > 0 and len(myd_files) > 0):
                return current_path
            
            # Stop if we hit a higher-level indicator
            dir_name = os.path.basename(current_path).lower()
            if dir_name in ['mysql', 'data', 'databases', 'db']:
                # Check if subdirectories contain actual DB files
                for item in os.listdir(current_path):
                    item_path = os.path.join(current_path, item)
                    if os.path.isdir(item_path):
                        sub_items = os.listdir(item_path)
                        if any(f.endswith('.frm') or f == 'db.opt' for f in sub_items):
                            return None  # The actual DB is in a subdirectory
            
            current_path = os.path.dirname(current_path)
            visited += 1
        
        return None

    def _find_postgresql_data_root(self, start_path: str) -> Optional[str]:
        """
        Find PostgreSQL data directory (PGDATA) by looking for PG_VERSION, postgresql.conf, etc.
        """
        current_path = start_path
        visited = 0
        max_depth = 5
        
        while current_path and os.path.isdir(current_path) and visited < max_depth:
            has_pg_version = os.path.exists(os.path.join(current_path, 'PG_VERSION'))
            has_pg_conf = os.path.exists(os.path.join(current_path, 'postgresql.conf'))
            has_base = os.path.isdir(os.path.join(current_path, 'base'))
            
            if has_pg_version or (has_pg_conf and has_base):
                return current_path
            
            current_path = os.path.dirname(current_path)
            visited += 1
        
        return None

    def _find_db_project_root(self, start_path: str) -> Optional[str]:
        """
        Walks up the directory tree to find indicators of a Database Project.
        Indicators:
        - Directory names: 'db', 'database', 'sql', 'migrations', 'seeders', 'dumps'
        - Presence of specific files: schema.yml, migrations.lock, etc.
        - Presence of many .sql files in a parent folder
        
        Returns None if only a single SQL file exists with no project indicators.
        """
        current_path = start_path
        visited = 0
        max_depth = 5
        
        while current_path and os.path.isdir(current_path) and visited < max_depth:
            dir_name = os.path.basename(current_path).lower()
            
            # Check directory name indicators
            if any(indicator in dir_name for indicator in ['db', 'database', 'sql', 'migration', 'dump', 'seed']):
                # Verify it actually contains SQL files
                sql_count = self._count_sql_files(current_path)
                if sql_count > 0:
                    # If this is the start_path and only 1 file, don't treat as project
                    if current_path == start_path and sql_count == 1:
                        return None
                    # If we found this by walking up (not start_path), check if total count is still just 1
                    if sql_count == 1:
                        return None
                    return current_path
            
            # Check for specific project files often found with DB dumps
            indicator_files = ['schema.yml', 'database.yml', 'migrations.json', 'structure.sql']
            if any(os.path.exists(os.path.join(current_path, f)) for f in indicator_files):
                return current_path
                
            # If we go too high and hit a generic src or app folder, stop looking for DB root specifically
            if dir_name in ['src', 'app', 'application', 'controllers', 'models']:
                break

            current_path = os.path.dirname(current_path)
            visited += 1
            
        return None

    def _get_sql_files_in_directory(self, directory: str) -> List[str]:
        """Lists SQL files in a specific directory (non-recursive)."""
        if not os.path.isdir(directory):
            return []
        files = []
        for f in os.listdir(directory):
            if f.endswith(tuple(self.sql_extensions)):
                files.append(f)
        return files

    def _count_sql_files(self, directory: str) -> int:
        """Counts SQL files recursively."""
        count = 0
        for root, _, files in os.walk(directory):
            for f in files:
                if f.endswith(tuple(self.sql_extensions)):
                    count += 1
        return count

    def _detect_dialect(self, content: str) -> str:
        """Heuristic detection of SQL dialect."""
        sample = content[:2000].upper()
        score_mysql = sum(1 for k in self.mysql_specific if k.upper() in sample)
        score_pg = sum(1 for k in self.postgres_specific if k.upper() in sample)
        
        if score_mysql > score_pg:
            return "MySQL/MariaDB"
        elif score_pg > score_mysql:
            return "PostgreSQL"
        else:
            return "Generic SQL / Unknown"

    def _detect_content_type(self, content: str) -> str:
        """Determines if file is Schema, Data, or Mixed."""
        sample = content.upper()
        has_create = 'CREATE TABLE' in sample
        has_insert = 'INSERT INTO' in sample
        has_procedure = 'CREATE PROCEDURE' in sample or 'CREATE FUNCTION' in sample
        
        if has_procedure:
            return "Stored Procedures/Functions"
        if has_create and not has_insert:
            return "Schema Only"
        if has_insert and not has_create:
            return "Data Only"
        if has_create and has_insert:
            return "Mixed Schema & Data"
        return "Unknown SQL Content"
