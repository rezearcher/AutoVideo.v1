# GPU Quota Increase Request Template

If you're unable to request quota increases through the Google Cloud Console, you can send an email directly to Google Cloud Support. Here's a template you can use:

---

**To:** cloud-support@google.com  
**Subject:** GPU Quota Increase Request for Project av-8675309

Dear Google Cloud Support Team,

I am writing to request a quota increase for our project. We need additional Vertex AI GPU quota to support our video generation workloads.

## Project Information
- **Project ID:** av-8675309
- **Project Number:** 939407899550
- **Organization:** (if applicable)

## Quota Increase Details

### Request 1:
- **Service:** aiplatform.googleapis.com
- **Quota:** custom_model_training_nvidia_t4_gpus
- **Region:** us-central1
- **Current Limit:** 0
- **Requested Limit:** 1
- **Justification:** Required for video generation in AutoVideo project. Our application needs GPU resources to process and generate videos efficiently.

### Request 2:
- **Service:** aiplatform.googleapis.com
- **Quota:** custom_model_training_nvidia_l4_gpus
- **Region:** us-central1
- **Current Limit:** 0
- **Requested Limit:** 1
- **Justification:** Same as above - required for video processing in AutoVideo project.

## Business Impact
Without these quota increases, our video generation pipeline is unable to process videos efficiently. We have already implemented TTS fallback mechanisms and other optimizations, but GPU access is essential for the video encoding portion of our workflow.

## Contact Information
- **Name:** [Your Name]
- **Email:** [Your Email]
- **Phone:** [Your Phone Number]

I appreciate your assistance with this request. Please let me know if you need any additional information.

Thank you,

[Your Name]
[Your Organization]

---

## Alternative Channels

If email doesn't work, you can also try:

1. **Google Cloud Support Console:**  
   https://console.cloud.google.com/support/cases/create?project=av-8675309

2. **Google Cloud Support Portal:**  
   https://support.google.com/cloud/answer/6282346

3. **Contact Sales:**  
   https://cloud.google.com/contact 