"""
Build Agent — TAD AI
Role: Ships code, MVPs, and technical deliverables based on approved specs.
Reads tasks from memory/build_queue/, writes builds to output/builds/,
and reports back to memory/all_reports/ for CEO review.
"""

import json
import os
import shutil
import sys
import datetime
import py_compile
from pathlib import Path
from typing import Dict, List, Tuple

__all__ = ["BuildAgent"]


class BuildAgent:
    """
    Production build agent for TAD AI.
    Processes queued build tasks, generates files, validates Python syntax,
    and writes structured reports for upstream decision makers.
    """

    def __init__(self, root_dir: str = r"C:\TAD") -> None:
        self.root = Path(root_dir).resolve()
        self.queue_dir = self.root / "memory" / "build_queue"
        self.output_dir = self.root / "output" / "builds"
        self.report_dir = self.root / "memory" / "all_reports"
        # Ensure required directories exist
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def get_queue(self) -> List[Path]:
        """Return sorted list of queued task files."""
        if not self.queue_dir.exists():
            return []
        return sorted([p for p in self.queue_dir.iterdir() if p.is_file()])

    def validate_python(self, file_path: Path) -> Tuple[bool, str]:
        """Validate Python syntax using py_compile."""
        try:
            py_compile.compile(str(file_path), doraise=True)
            return True, "Syntax OK"
        except py_compile.PyCompileError as e:
            return False, str(e)

    def process_task(self, task_path: Path) -> Dict:
        """Process a single build task and return a report dict."""
        task_name = task_path.stem
        timestamp = datetime.datetime.now().isoformat()
        try:
            with open(task_path, "r", encoding="utf-8") as f:
                task_data = json.load(f)
        except Exception as e:
            return {
                "task": task_name,
                "timestamp": timestamp,
                "status": "failed",
                "error": f"Could not parse task: {e}",
            }

        code = task_data.get("code", "")
        build_file = self.output_dir / f"{task_name}.py"

        try:
            with open(build_file, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            return {
                "task": task_name,
                "timestamp": timestamp,
                "status": "failed",
                "error": f"Could not write build: {e}",
            }

        valid, message = self.validate_python(build_file)
        status = "success" if valid else "build_error"
        report = {
            "task": task_name,
            "timestamp": timestamp,
            "status": status,
            "output_file": str(build_file),
            "validation": message,
        }
        if not valid:
            report["error"] = message
        return report

    def run(self) -> None:
        """Process all queued tasks and write reports."""
        queue = self.get_queue()
        if not queue:
            print("No tasks in queue.")
            return

        for task_path in queue:
            print(f"Processing: {task_path.name}")
            report = self.process_task(task_path)
            report_file = self.report_dir / f"{task_path.stem}_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"  Status: {report['status']}")
            # Move processed task to processed