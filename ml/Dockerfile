FROM scratch AS models
ADD --checksum=sha256:c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212 --chmod=0644 https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt /yolov8n-pose.pt
ADD --checksum=sha256:1f47a78bf100391c2a140b7ac73a1caae18c32779be7d310658112f7ac9aa78a --chmod=0644 https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt /yolov8s.pt
ADD --checksum=sha256:f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36 --chmod=0644 https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt /yolov8n.pt
COPY --chmod=0644 models/shoplifting_classifier.pt models/shoplifting_classifier.meta.json /
