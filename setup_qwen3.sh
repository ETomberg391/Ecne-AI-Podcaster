#!/bin/bash
# Setup script for Qwen3 TTS API integration
# This script sets up the EcneAI-Qwen-3-TTS-api service

# Note: set -e removed to allow fallback behavior for PyTorch installation

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
QWEN3_DIR="$SCRIPT_DIR/EcneAI-Qwen-3-TTS-api"

print_info "Setting up Qwen3 TTS API..."
print_info "Project directory: $SCRIPT_DIR"

# Check if Qwen3 directory exists
if [ ! -d "$QWEN3_DIR" ]; then
    print_error "Qwen3 TTS API directory not found at: $QWEN3_DIR"
    print_info "Please ensure the EcneAI-Qwen-3-TTS-api folder exists."
    print_info "You can clone it with: git clone https://github.com/ETomberg391/EcneAI-Qwen-3-TTS-api.git"
    exit 1
fi

print_success "Found Qwen3 TTS API at: $QWEN3_DIR"

# Check Python version - use 'python' command if available, fall back to 'python3'
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
print_info "Python version: $PYTHON_VERSION (using $PYTHON_CMD)"

# Check for GPU
if command -v nvidia-smi &> /dev/null; then
    print_success "NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    USE_GPU=true
else
    print_warning "No NVIDIA GPU detected. Will use CPU (slower)."
    USE_GPU=false
fi

# Navigate to Qwen3 directory
cd "$QWEN3_DIR"

# Create virtual environment if it doesn't exist or if it's broken
if [ ! -d "venv" ]; then
    print_info "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
else
    # Check if existing venv is working properly
    print_info "Checking existing virtual environment..."
    source venv/bin/activate
    if ! pip --version > /dev/null 2>&1; then
        print_warning "Existing virtual environment is broken (pip not working)"
        print_info "Recreating virtual environment..."
        deactivate
        rm -rf venv
        $PYTHON_CMD -m venv venv
    else
        print_success "Virtual environment is working"
    fi
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip (ensure pip exists)
print_info "Upgrading pip..."
if ! pip install --upgrade pip setuptools wheel; then
    print_warning "Failed to upgrade pip, attempting to ensure pip is installed..."
    python -m ensurepip --upgrade
    pip install --upgrade pip setuptools wheel
fi

# Check Python version
PYTHON_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')
print_info "Python version: $PYTHON_MAJOR.$PYTHON_MINOR"

# Install PyTorch based on GPU availability
if [ "$USE_GPU" = true ]; then
    print_info "Installing PyTorch with CUDA support..."
    # Try CUDA version first, fall back to default if it fails (for newer Python versions)
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 || {
        print_warning "Failed to install CUDA-specific PyTorch (may not be available for Python $PYTHON_MAJOR.$PYTHON_MINOR)"
        print_info "Falling back to default PyTorch installation..."
        pip install torch torchvision torchaudio
    }
else
    print_info "Installing PyTorch (CPU only)..."
    # Try CPU version first, fall back to default if it fails (for newer Python versions)
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu || {
        print_warning "Failed to install CPU-specific PyTorch (may not be available for Python $PYTHON_MAJOR.$PYTHON_MINOR)"
        print_info "Falling back to default PyTorch installation..."
        pip install torch torchvision torchaudio
    }
fi

# Install Qwen3 TTS requirements
if [ -f "requirements.txt" ]; then
    print_info "Installing Qwen3 TTS requirements..."
    pip install -r requirements.txt
else
    print_error "requirements.txt not found in $QWEN3_DIR"
    exit 1
fi

# Install onnxruntime-gpu if using GPU
if [ "$USE_GPU" = true ]; then
    print_info "Installing ONNX Runtime GPU..."
    pip uninstall -y onnxruntime
    pip install onnxruntime-gpu
fi

print_success "Qwen3 TTS API setup complete!"

# Create systemd service file (optional)
echo ""
print_info "Would you like to create a systemd service to auto-start Qwen3 TTS? (y/n)"
read -r CREATE_SERVICE

if [[ "$CREATE_SERVICE" =~ ^[Yy]$ ]]; then
    SERVICE_FILE="/etc/systemd/system/qwen3-tts.service"
    
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Qwen3 TTS API Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$QWEN3_DIR
Environment=PATH=$QWEN3_DIR/venv/bin
ExecStart=$QWEN3_DIR/venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    print_success "Systemd service created at: $SERVICE_FILE"
    print_info "Start the service with: sudo systemctl start qwen3-tts"
    print_info "Enable auto-start with: sudo systemctl enable qwen3-tts"
fi

# Create startup script
cat > "$SCRIPT_DIR/start_qwen3.sh" <<'EOF'
#!/bin/bash
# Start Qwen3 TTS API Server

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
QWEN3_DIR="$SCRIPT_DIR/EcneAI-Qwen-3-TTS-api"

cd "$QWEN3_DIR"
source venv/bin/activate

echo "Starting Qwen3 TTS API Server..."
echo "API will be available at: http://127.0.0.1:8000"
echo "Press Ctrl+C to stop"
echo ""

python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
EOF

chmod +x "$SCRIPT_DIR/start_qwen3.sh"
print_success "Created startup script: start_qwen3.sh"

# Create test script
cat > "$SCRIPT_DIR/test_qwen3.sh" <<'EOF'
#!/bin/bash
# Test Qwen3 TTS API

API_URL="http://127.0.0.1:8000"

echo "Testing Qwen3 TTS API at $API_URL..."
echo ""

# Health check
echo "1. Health Check:"
curl -s "$API_URL/health" | $PYTHON_CMD -m json.tool 2>/dev/null || curl -s "$API_URL/health"
echo ""

# Test TTS with Ryan voice
echo ""
echo "2. Testing TTS with Ryan voice:"
curl -s -X POST "$API_URL/v1/audio/speech" \
  -F "model=qwen3-tts-1.7b-customvoice" \
  -F "input=Hello, this is a test of the Qwen3 text to speech system." \
  -F "voice=Ryan" \
  -F "response_format=wav" \
  -F "speed=1.0" \
  --output /tmp/qwen3_test.wav

if [ -f "/tmp/qwen3_test.wav" ] && [ -s "/tmp/qwen3_test.wav" ]; then
    echo "✓ Audio generated successfully: /tmp/qwen3_test.wav"
    ls -lh /tmp/qwen3_test.wav
else
    echo "✗ Failed to generate audio"
fi

echo ""
echo "Test complete!"
EOF

chmod +x "$SCRIPT_DIR/test_qwen3.sh"
print_success "Created test script: test_qwen3.sh"

# Create environment file update script
cat > "$SCRIPT_DIR/update_env_for_qwen3.sh" <<EOF
#!/bin/bash
# Update .env file for Qwen3 TTS

ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "\$ENV_FILE" ]; then
    echo "Creating new .env file..."
    cp "$SCRIPT_DIR/settings/env.example" "\$ENV_FILE"
fi

# Update TTS provider to Qwen3
sed -i 's/^TTS_PROVIDER=.*/TTS_PROVIDER="qwen3"/' "\$ENV_FILE"

echo "Updated \$ENV_FILE for Qwen3 TTS"
echo "TTS_PROVIDER is now set to 'qwen3'"
EOF

chmod +x "$SCRIPT_DIR/update_env_for_qwen3.sh"

# Summary
echo ""
echo "=========================================="
echo "  Qwen3 TTS Setup Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo ""
echo "1. Start the Qwen3 TTS server:"
echo "   ./start_qwen3.sh"
echo ""
echo "2. In a new terminal, test the API:"
echo "   ./test_qwen3.sh"
echo ""
echo "3. Update your .env file:"
echo "   ./update_env_for_qwen3.sh"
echo ""
echo "4. Use Qwen3 voices in your podcasts:"
echo "   python script_builder.py --script your_script.txt --host-voice Ryan --guest-voice Serena"
echo ""
echo "Available Qwen3 Voices:"
echo "  Male: Ryan, Aiden (English), Dylan, Uncle_Fu, Eric (Chinese)"
echo "  Female: Serena, Vivian (Chinese/English), Sohee (Korean), Ono_Anna (Japanese)"
echo ""
echo "For voice cloning, use the API directly:"
echo "  curl -X POST http://localhost:8000/v1/voices \\"
echo "    -F 'name=My Voice' \\"
echo "    -F 'voice_sample=@sample.wav' \\"
echo "    -F 'voice_sample_text=Original text'"
echo ""

# Deactivate virtual environment
deactivate
