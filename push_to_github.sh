#!/bin/bash

# Script to push code to GitHub
# This will prompt you for your GitHub credentials

echo "=========================================="
echo "Pushing to GitHub Repository"
echo "=========================================="
echo ""
echo "Repository: https://github.com/Zayn-Suleman/loan_preQualification.git"
echo "Branch: main"
echo ""
echo "You will be prompted for:"
echo "  Username: Your GitHub username"
echo "  Password: Your Personal Access Token (NOT your GitHub password)"
echo ""
echo "📝 To create a Personal Access Token:"
echo "   1. Go to GitHub.com"
echo "   2. Settings → Developer settings → Personal access tokens → Tokens (classic)"
echo "   3. Generate new token with 'repo' scope"
echo "   4. Copy the token and paste it when prompted for password"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."
echo ""

# Push to GitHub
echo "Pushing to origin main..."
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ Successfully pushed to GitHub!"
    echo "=========================================="
    echo ""
    echo "View your repository at:"
    echo "https://github.com/Zayn-Suleman/loan_preQualification"
    echo ""
    echo "Check CI/CD pipeline status at:"
    echo "https://github.com/Zayn-Suleman/loan_preQualification/actions"
else
    echo ""
    echo "=========================================="
    echo "❌ Push failed!"
    echo "=========================================="
    echo ""
    echo "Common issues:"
    echo "1. Invalid credentials - Make sure you're using a Personal Access Token, not your password"
    echo "2. Token doesn't have 'repo' scope"
    echo "3. Network issues"
    echo ""
    echo "For detailed help, see GITHUB_SETUP.md"
fi
