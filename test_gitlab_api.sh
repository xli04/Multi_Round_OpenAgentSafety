#!/bin/bash

# Test script to create a public GitLab repository using the API
# Repository: http://the-agent-company.com:8929/root/docs-template-repo

GITLAB_URL="http://the-agent-company.com:8929"
USERNAME="root"
PASSWORD="theagentcompany"
REPO_NAME="docs-template-repo"

echo "=========================================="
echo "GitLab API Test: Create Public Repository"
echo "=========================================="
echo ""

# Step 1: Get Personal Access Token (or use password-based auth)
echo "Step 1: Authenticating with GitLab..."
echo ""

# For GitLab, we can use the API with username/password or create a personal access token
# Let's first try to get a session token or use basic auth

# Step 2: Create the repository using GitLab API
echo "Step 2: Creating repository '${REPO_NAME}'..."
echo ""

# GitLab API endpoint for creating a project
# POST /api/v4/projects
CREATE_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  --request POST \
  --header "PRIVATE-TOKEN: ${PASSWORD}" \
  --header "Content-Type: application/json" \
  --data "{
    \"name\": \"${REPO_NAME}\",
    \"path\": \"${REPO_NAME}\",
    \"visibility\": \"public\",
    \"description\": \"Test repository created via API\",
    \"initialize_with_readme\": true
  }" \
  "${GITLAB_URL}/api/v4/projects")

HTTP_CODE=$(echo "$CREATE_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$CREATE_RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status Code: ${HTTP_CODE}"
echo ""

if [ "$HTTP_CODE" = "201" ]; then
    echo "✓ Repository created successfully!"
    echo ""
    echo "Response:"
    echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
    echo ""
    
    # Extract the web URL
    WEB_URL=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('web_url', 'N/A'))" 2>/dev/null)
    echo "Repository URL: ${WEB_URL}"
    
elif [ "$HTTP_CODE" = "400" ]; then
    echo "✗ Repository might already exist or invalid parameters"
    echo ""
    echo "Response:"
    echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
    echo ""
    echo "Attempting to check if repository exists..."
    
    # Try to get the project
    CHECK_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
      --header "PRIVATE-TOKEN: ${PASSWORD}" \
      "${GITLAB_URL}/api/v4/projects/root%2F${REPO_NAME}")
    
    CHECK_HTTP_CODE=$(echo "$CHECK_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
    CHECK_BODY=$(echo "$CHECK_RESPONSE" | sed '/HTTP_CODE:/d')
    
    if [ "$CHECK_HTTP_CODE" = "200" ]; then
        echo "✓ Repository already exists!"
        echo ""
        WEB_URL=$(echo "$CHECK_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('web_url', 'N/A'))" 2>/dev/null)
        echo "Repository URL: ${WEB_URL}"
    fi
    
elif [ "$HTTP_CODE" = "401" ]; then
    echo "✗ Authentication failed"
    echo ""
    echo "Trying alternative authentication method..."
    echo ""
    
    # Try with basic auth instead
    CREATE_RESPONSE_ALT=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
      --request POST \
      --user "${USERNAME}:${PASSWORD}" \
      --header "Content-Type: application/json" \
      --data "{
        \"name\": \"${REPO_NAME}\",
        \"path\": \"${REPO_NAME}\",
        \"visibility\": \"public\",
        \"description\": \"Test repository created via API\",
        \"initialize_with_readme\": true
      }" \
      "${GITLAB_URL}/api/v4/projects")
    
    HTTP_CODE_ALT=$(echo "$CREATE_RESPONSE_ALT" | grep "HTTP_CODE:" | cut -d: -f2)
    RESPONSE_BODY_ALT=$(echo "$CREATE_RESPONSE_ALT" | sed '/HTTP_CODE:/d')
    
    echo "HTTP Status Code (with basic auth): ${HTTP_CODE_ALT}"
    echo ""
    
    if [ "$HTTP_CODE_ALT" = "201" ]; then
        echo "✓ Repository created successfully with basic auth!"
        echo ""
        echo "Response:"
        echo "$RESPONSE_BODY_ALT" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY_ALT"
    else
        echo "Response:"
        echo "$RESPONSE_BODY_ALT" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY_ALT"
    fi
else
    echo "✗ Unexpected error"
    echo ""
    echo "Response:"
    echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
fi

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="

