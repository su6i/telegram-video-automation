#!/bin/bash

# 1. Generate/Update Viewer
echo "🔄 Updating local viewer and patching links..."
python3 scripts/generate_viewer.py

# 2. Check result
if [ $? -eq 0 ]; then
    echo "✅ Local viewer updated successfully!"
    echo "🚀 Starting server at http://localhost:8000"
    echo "👉 Opening your browser now..."
    echo "Shift + C to stop the server."
    
    # 3. Open browser automatically (Mac only)
    open http://localhost:8000 &
    
    # 4. Start local server
    python3 -m http.server 8000
else
    echo "❌ Failed to generate local viewer."
fi
