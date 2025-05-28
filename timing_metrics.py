import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TimingMetrics:
    def __init__(self):
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.phase_times: Dict[str, float] = {}
        self.current_phase: Optional[str] = None
        self.phase_start_time: Optional[datetime] = None
        self.total_duration: Optional[float] = None

    def start_pipeline(self):
        """Start timing the entire pipeline."""
        self.start_time = datetime.now()
        logger.info("Pipeline timing started")

    def end_pipeline(self):
        """End timing the entire pipeline."""
        self.end_time = datetime.now()
        if self.start_time:
            self.total_duration = (self.end_time - self.start_time).total_seconds()
            logger.info(f"Pipeline completed in {self.total_duration:.2f} seconds")

    def start_phase(self, phase_name: str):
        """Start timing a specific phase."""
        self.current_phase = phase_name
        self.phase_start_time = datetime.now()
        logger.info(f"Starting phase: {phase_name}")

    def end_phase(self):
        """End timing the current phase."""
        if self.current_phase and self.phase_start_time:
            duration = (datetime.now() - self.phase_start_time).total_seconds()
            self.phase_times[self.current_phase] = duration
            logger.info(
                f"Phase {self.current_phase} completed in {duration:.2f} seconds"
            )
            self.current_phase = None
            self.phase_start_time = None

    def get_metrics(self) -> dict:
        """Get all timing metrics."""
        return {
            "total_duration": self.total_duration,
            "phase_times": self.phase_times,
            "current_phase": self.current_phase,
            "current_phase_duration": (
                (datetime.now() - self.phase_start_time).total_seconds()
                if self.current_phase and self.phase_start_time
                else None
            ),
        }
