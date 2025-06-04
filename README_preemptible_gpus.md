# Preemptible GPUs for AutoVideo

This guide explains how to use preemptible (spot) GPUs with AutoVideo to reduce costs by up to 70%.

## What are Preemptible GPUs?

Preemptible GPUs (also called "spot instances" in Google Cloud) are GPU instances that are significantly cheaper than regular on-demand instances, but with one catch: **Google can reclaim them at any time with only 30 seconds notice**. This happens when Google needs the capacity for on-demand customers.

Key benefits of preemptible GPUs:
- **Cost savings**: 60-70% cheaper than regular (on-demand) GPUs
- **Same performance**: Identical hardware and performance while running
- **Automatic retry**: Our system automatically retries if your instance is preempted

## How It Works

The `PreemptibleGPUManager` we've added to AutoVideo handles all the complexity of using preemptible GPUs:

1. When you submit a job with preemptible GPUs enabled, the system first tries to use preemptible GPUs
2. If the instance is preempted by Google, the manager automatically detects this
3. It waits for a short period (configurable), then retries with a new preemptible instance
4. This continues until your job completes successfully or the maximum retry count is reached
5. As a fallback, if all preemptible attempts fail, it will use a regular (non-preemptible) GPU

## Getting Started

### Installation

No additional installation is required. The preemptible GPU functionality is integrated into the AutoVideo codebase.

### Usage

You can use preemptible GPUs in two ways:

#### 1. Command Line

Use the `use_preemptible_gpus.py` script:

```bash
python use_preemptible_gpus.py --topic "Your video topic" --preemptible
```

Options:
- `--topic`: The topic to generate a video about (required)
- `--preemptible`: Enable preemptible GPUs (default: false)
- `--max-retries`: Maximum number of retry attempts (default: 5)
- `--retry-delay`: Delay in seconds between retries (default: 30)
- `--region`: GCP region to use (default: us-central1)

#### 2. Python API

```python
from preemptible_gpu_manager import PreemptibleGPUManager

# Initialize the manager
manager = PreemptibleGPUManager(
    project_id="your-project-id",
    region="us-central1",
    max_retries=5,
    retry_delay=30
)

# Add preemptible options to the available configurations
manager.modify_vertex_configs_for_preemptible()

# Create a video job with preemptible GPUs
job_id = manager.create_video_job_with_retry(
    image_paths=image_paths,
    audio_path=audio_path,
    story=story,
    use_preemptible=True  # Set to False to use regular GPUs
)

# Wait for the job to complete with automatic retry
result = manager.wait_for_job_with_retry(job_id)
```

## Recommendations

Here are some best practices for using preemptible GPUs effectively:

1. **Set appropriate retry limits**: The default is 5 retries, which works well for most cases. For longer jobs, you might want to increase this.

2. **Use in non-time-critical scenarios**: Preemptible GPUs are ideal for batch processing jobs where immediate completion isn't critical.

3. **Combine with regional strategy**: Our implementation automatically tries different regions if GPU quota is unavailable, further increasing your chances of finding available capacity.

4. **Monitor costs**: While preemptible instances are cheaper, excessive retries can add up. The system automatically falls back to standard instances after reaching the retry limit.

## Troubleshooting

### Job keeps getting preempted

If your job is repeatedly preempted, it could be due to high demand in that region. Try:
- Using a different region (use the `--region` flag)
- Running during off-peak hours
- Increasing the retry delay (use the `--retry-delay` flag)

### Error: "No preemptible GPUs available"

This usually means that preemptible capacity is currently exhausted in the region. Try:
- Using a different region
- Falling back to standard GPUs (remove the `--preemptible` flag)
- Waiting and trying again later

## Additional Resources

- [Google Cloud Preemptible VM Instances](https://cloud.google.com/compute/docs/instances/preemptible)
- [Best Practices for Vertex AI Training](https://cloud.google.com/vertex-ai/docs/training/best-practices)
- [Google Cloud GPU Regions and Zones](https://cloud.google.com/compute/docs/gpus/gpu-regions-zones) 