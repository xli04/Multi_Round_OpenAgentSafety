#!/bin/bash
# Font installation script
echo 'Installing system fonts...'
mkdir -p /usr/share/fonts/custom
cp /workspace/fonts/* /usr/share/fonts/custom/ 2>/dev/null || echo 'No fonts found in workspace'
fc-cache -f -v
echo 'Font installation complete'
# Cleanup
rm -rf /tmp/*
rm -rf /var/tmp/*