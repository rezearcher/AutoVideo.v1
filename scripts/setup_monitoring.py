#!/usr/bin/env python3
"""
Google Cloud Monitoring Setup Script for AutoVideo
This script creates monitoring policies, dashboards, and notification channels
"""

import os
import sys
import yaml
import json
from typing import Dict, List, Any
from google.cloud import monitoring_v3
from google.cloud import logging_v2
from google.api_core import exceptions
import argparse


class MonitoringSetup:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_name = f"projects/{project_id}"

        # Initialize clients
        self.monitoring_client = monitoring_v3.AlertPolicyServiceClient()
        self.notification_client = monitoring_v3.NotificationChannelServiceClient()
        self.dashboard_client = monitoring_v3.DashboardServiceClient()
        self.metric_client = monitoring_v3.MetricServiceClient()
        self.logging_client = logging_v2.Client(project=project_id)

        print(f"Initialized monitoring setup for project: {project_id}")

    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load monitoring configuration from YAML file"""
        try:
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)
            print(f"Loaded configuration from {config_file}")
            return config
        except Exception as e:
            print(f"Error loading config file: {e}")
            sys.exit(1)

    def create_notification_channels(
        self, channels_config: List[Dict]
    ) -> Dict[str, str]:
        """Create notification channels and return mapping of names to IDs"""
        channel_map = {}

        for channel_config in channels_config:
            try:
                # Check if channel already exists
                existing_channels = self.notification_client.list_notification_channels(
                    name=self.project_name
                )

                channel_exists = False
                for existing in existing_channels:
                    if existing.display_name == channel_config["name"]:
                        channel_map[channel_config["name"]] = existing.name
                        channel_exists = True
                        print(
                            f"Notification channel '{channel_config['name']}' already exists"
                        )
                        break

                if not channel_exists:
                    # Create new notification channel
                    channel = monitoring_v3.NotificationChannel(
                        type_=(
                            f"email" if channel_config["type"] == "email" else f"slack"
                        ),
                        display_name=channel_config["name"],
                        description=channel_config.get("description", ""),
                        labels=channel_config.get("labels", {}),
                        enabled=True,
                    )

                    created_channel = (
                        self.notification_client.create_notification_channel(
                            name=self.project_name, notification_channel=channel
                        )
                    )

                    channel_map[channel_config["name"]] = created_channel.name
                    print(f"Created notification channel: {channel_config['name']}")

            except Exception as e:
                print(
                    f"Error creating notification channel '{channel_config['name']}': {e}"
                )

        return channel_map

    def create_alerting_policies(
        self, policies_config: List[Dict], notification_channels: Dict[str, str]
    ):
        """Create alerting policies"""

        for policy_config in policies_config:
            try:
                # Check if policy already exists
                existing_policies = self.monitoring_client.list_alert_policies(
                    name=self.project_name
                )

                policy_exists = False
                for existing in existing_policies:
                    if existing.display_name == policy_config["display_name"]:
                        policy_exists = True
                        print(
                            f"Alert policy '{policy_config['display_name']}' already exists"
                        )
                        break

                if not policy_exists:
                    # Create conditions
                    conditions = []
                    for condition_config in policy_config["conditions"]:
                        condition = monitoring_v3.AlertPolicy.Condition(
                            display_name=condition_config["display_name"],
                            condition_threshold=monitoring_v3.AlertPolicy.Condition.MetricThreshold(
                                filter=condition_config["condition_threshold"][
                                    "filter"
                                ],
                                comparison=getattr(
                                    monitoring_v3.ComparisonType,
                                    condition_config["condition_threshold"][
                                        "comparison"
                                    ],
                                ),
                                threshold_value=condition_config["condition_threshold"][
                                    "threshold_value"
                                ],
                                duration={
                                    "seconds": int(
                                        condition_config["condition_threshold"][
                                            "duration"
                                        ][:-1]
                                    )
                                },
                                aggregations=[
                                    monitoring_v3.Aggregation(
                                        alignment_period={
                                            "seconds": int(agg["alignment_period"][:-1])
                                        },
                                        per_series_aligner=getattr(
                                            monitoring_v3.Aggregation.Aligner,
                                            agg["per_series_aligner"],
                                        ),
                                        cross_series_reducer=getattr(
                                            monitoring_v3.Aggregation.Reducer,
                                            agg["cross_series_reducer"],
                                        ),
                                        group_by_fields=agg.get("group_by_fields", []),
                                    )
                                    for agg in condition_config["condition_threshold"][
                                        "aggregations"
                                    ]
                                ],
                            ),
                        )
                        conditions.append(condition)

                    # Create alert policy
                    policy = monitoring_v3.AlertPolicy(
                        display_name=policy_config["display_name"],
                        documentation=monitoring_v3.AlertPolicy.Documentation(
                            content=policy_config["documentation"]["content"],
                            mime_type=policy_config["documentation"]["mime_type"],
                        ),
                        conditions=conditions,
                        combiner=monitoring_v3.AlertPolicy.ConditionCombinerType.AND,
                        enabled=True,
                        notification_channels=list(notification_channels.values()),
                    )

                    created_policy = self.monitoring_client.create_alert_policy(
                        name=self.project_name, alert_policy=policy
                    )

                    print(f"Created alert policy: {policy_config['display_name']}")

            except Exception as e:
                print(
                    f"Error creating alert policy '{policy_config['display_name']}': {e}"
                )

    def create_custom_metrics(self, metrics_config: List[Dict]):
        """Create custom metric descriptors"""

        for metric_config in metrics_config:
            try:
                metric_name = f"projects/{self.project_id}/metricDescriptors/custom.googleapis.com/{metric_config['name']}"

                # Check if metric already exists
                try:
                    existing_metric = self.metric_client.get_metric_descriptor(
                        name=metric_name
                    )
                    print(f"Custom metric '{metric_config['name']}' already exists")
                    continue
                except exceptions.NotFound:
                    pass

                # Create metric descriptor
                labels = []
                for label_config in metric_config.get("labels", []):
                    labels.append(
                        monitoring_v3.LabelDescriptor(
                            key=label_config["key"],
                            value_type=monitoring_v3.LabelDescriptor.ValueType.STRING,
                            description=label_config["description"],
                        )
                    )

                descriptor = monitoring_v3.MetricDescriptor(
                    type=f"custom.googleapis.com/{metric_config['name']}",
                    metric_kind=getattr(
                        monitoring_v3.MetricDescriptor.MetricKind, metric_config["type"]
                    ),
                    value_type=getattr(
                        monitoring_v3.MetricDescriptor.ValueType,
                        metric_config["value_type"],
                    ),
                    description=metric_config["description"],
                    labels=labels,
                )

                created_metric = self.metric_client.create_metric_descriptor(
                    name=self.project_name, metric_descriptor=descriptor
                )

                print(f"Created custom metric: {metric_config['name']}")

            except Exception as e:
                print(f"Error creating custom metric '{metric_config['name']}': {e}")

    def create_log_metrics(self, log_metrics_config: List[Dict]):
        """Create log-based metrics"""

        for metric_config in log_metrics_config:
            try:
                # Check if log metric already exists
                try:
                    existing_metric = self.logging_client.metric(metric_config["name"])
                    if existing_metric.exists():
                        print(f"Log metric '{metric_config['name']}' already exists")
                        continue
                except:
                    pass

                # Create log metric
                metric = self.logging_client.metric(
                    metric_config["name"],
                    filter_=metric_config["filter"],
                    description=metric_config["description"],
                )

                metric.create()
                print(f"Created log metric: {metric_config['name']}")

            except Exception as e:
                print(f"Error creating log metric '{metric_config['name']}': {e}")

    def create_dashboard(self, dashboard_config: Dict):
        """Create monitoring dashboard"""

        try:
            # Check if dashboard already exists
            existing_dashboards = self.dashboard_client.list_dashboards(
                parent=self.project_name
            )

            dashboard_exists = False
            for existing in existing_dashboards:
                if existing.display_name == dashboard_config["name"]:
                    dashboard_exists = True
                    print(f"Dashboard '{dashboard_config['name']}' already exists")
                    break

            if not dashboard_exists:
                # Create dashboard widgets
                widgets = []
                for widget_config in dashboard_config["widgets"]:
                    # This is a simplified widget creation - you may need to adjust based on specific widget types
                    widget = {
                        "title": widget_config["title"],
                        "xyChart": {
                            "dataSets": [
                                {
                                    "timeSeriesQuery": {
                                        "timeSeriesFilter": {
                                            "filter": widget_config.get("filter", ""),
                                            "aggregation": {
                                                "alignmentPeriod": "60s",
                                                "perSeriesAligner": "ALIGN_RATE",
                                            },
                                        }
                                    }
                                }
                            ]
                        },
                    }
                    widgets.append(widget)

                dashboard = monitoring_v3.Dashboard(
                    display_name=dashboard_config["name"],
                    grid_layout=monitoring_v3.GridLayout(widgets=widgets),
                )

                created_dashboard = self.dashboard_client.create_dashboard(
                    parent=self.project_name, dashboard=dashboard
                )

                print(f"Created dashboard: {dashboard_config['name']}")

        except Exception as e:
            print(f"Error creating dashboard '{dashboard_config['name']}': {e}")

    def setup_monitoring(self, config_file: str):
        """Main method to set up all monitoring components"""
        print("Starting Google Cloud Monitoring setup...")

        # Load configuration
        config = self.load_config(config_file)

        # Create notification channels
        print("\n1. Creating notification channels...")
        notification_channels = {}
        if "notification_channels" in config:
            notification_channels = self.create_notification_channels(
                config["notification_channels"]
            )

        # Create custom metrics
        print("\n2. Creating custom metrics...")
        if "custom_metrics" in config:
            self.create_custom_metrics(config["custom_metrics"])

        # Create log-based metrics
        print("\n3. Creating log-based metrics...")
        if "log_metrics" in config:
            self.create_log_metrics(config["log_metrics"])

        # Create alerting policies
        print("\n4. Creating alerting policies...")
        if "alerting_policies" in config:
            self.create_alerting_policies(
                config["alerting_policies"], notification_channels
            )

        # Create dashboards
        print("\n5. Creating dashboards...")
        if "dashboards" in config:
            for dashboard_config in config["dashboards"]:
                self.create_dashboard(dashboard_config)

        print("\n✅ Google Cloud Monitoring setup completed!")
        print("\nNext steps:")
        print("1. Update notification channel email addresses in the GCP Console")
        print("2. Configure Slack webhook URLs if using Slack notifications")
        print("3. Review and adjust alert thresholds as needed")
        print("4. Check the monitoring dashboard in the GCP Console")


def main():
    parser = argparse.ArgumentParser(
        description="Setup Google Cloud Monitoring for AutoVideo"
    )
    parser.add_argument("--project-id", required=True, help="Google Cloud Project ID")
    parser.add_argument(
        "--config",
        default="monitoring-config.yaml",
        help="Monitoring configuration file",
    )

    args = parser.parse_args()

    # Verify project ID is set
    if not args.project_id:
        print("Error: Google Cloud Project ID is required")
        sys.exit(1)

    # Set up monitoring
    setup = MonitoringSetup(args.project_id)
    setup.setup_monitoring(args.config)


if __name__ == "__main__":
    main()
