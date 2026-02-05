#!/bin/bash

# ============================================
# Ecne AI Podcaster - Qwen3 TTS Installer
# ============================================
# This installer sets up the Ecne AI Podcaster with Qwen3 TTS as the primary provider.
# Qwen3 TTS runs natively (no Docker required) and provides high-quality voice synthesis
# with voice cloning capabilities.
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect Python command (prefer 'python' over 'python3' if available)
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
    PIP_CMD="pip"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    PIP_CMD="pip3"
else
    echo "ERROR: Neither 'python' nor 'python3' found. Please install Python."
    exit 1
fi

# ============================================
# Helper Functions
# ============================================

print_header() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Ecne AI Podcaster - Qwen3 TTS Setup                ║"
    echo "║                                                              ║"
    echo "║  🎙️  Primary TTS: Qwen3 (Native, No Docker)                  ║"
    echo "║  🎯  Features: High-quality synthesis + Voice Cloning        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_section() {
    echo -e "\n${MAGENTA}▶ $1${NC}"
    echo -e "${MAGENTA}$(printf '=%.0s' $(seq 1 $((${#1}+3))))${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ============================================
# Pre-flight Checks
# ============================================

check_system() {
    print_section "System Requirements Check"
    
    # Check OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        print_success "Linux detected"
    else
        print_error "This installer is designed for Linux systems only."
        exit 1
    fi
    
    # Check for required commands
    local required_commands=("$PYTHON_CMD" "$PIP_CMD" "git")
    local missing_commands=()
    
    for cmd in "${required_commands[@]}"; do
        if command_exists "$cmd"; then
            print_success "$cmd is installed"
        else
            missing_commands+=("$cmd")
            print_error "$cmd is NOT installed"
        fi
    done
    
    if [ ${#missing_commands[@]} -ne 0 ]; then
        print_section "Installing Missing Dependencies"
        echo "The following packages need to be installed: ${missing_commands[*]}"
        echo ""
        
        if command_exists apt; then
            print_info "Detected apt package manager"
            echo "Run: sudo apt update && sudo apt install -y python3 python3-pip python3-venv git"
            echo ""
            read -p "Would you like to install them now? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo apt update
                sudo apt install -y python3 python3-pip python3-venv git
            else
                print_error "Please install the missing dependencies and run the installer again."
                exit 1
            fi
        elif command_exists yum; then
            print_info "Detected yum package manager"
            echo "Run: sudo yum install -y python3 python3-pip git"
            read -p "Would you like to install them now? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo yum install -y python3 python3-pip git
            else
                print_error "Please install the missing dependencies and run the installer again."
                exit 1
            fi
        else
            print_error "Could not detect package manager. Please install manually: ${missing_commands[*]}"
            exit 1
        fi
    fi
    
    # Check Python version (3.8+)
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    print_info "Python version: $PYTHON_VERSION"
    
    # Check for CUDA/GPU
    if command_exists nvidia-smi; then
        print_success "NVIDIA GPU detected"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    else
        print_warning "No NVIDIA GPU detected - Qwen3 will run on CPU (slower)"
    fi
    
    # Check for Chrome (required for some features)
    if command_exists google-chrome || command_exists chromium || command_exists chromium-browser; then
        print_success "Chrome/Chromium browser detected"
    else
        print_warning "Chrome/Chromium not detected. Some features may require it."
    fi
}

# ============================================
# Setup Functions
# ============================================

setup_host_venv() {
    print_section "Setting Up Host Python Environment"
    
    cd "$SCRIPT_DIR"
    
    # Create virtual environment
    if [ ! -d "venv" ]; then
        print_info "Creating Python virtual environment..."
        $PYTHON_CMD -m venv venv
        print_success "Virtual environment created"
    else
        print_info "Virtual environment already exists"
    fi
    
    # Activate and upgrade pip
    source venv/bin/activate
    pip install --upgrade pip
    print_success "Pip upgraded"
    
    # Install host requirements
    if [ -f "requirements_host.txt" ]; then
        print_info "Installing host dependencies..."
        pip install -r requirements_host.txt
        print_success "Host dependencies installed"
    else
        print_warning "requirements_host.txt not found - installing core dependencies"
        pip install requests beautifulsoup4 praw pydub python-dotenv pyyaml openai
    fi
    
    # Install ChromeDriver if needed
    print_info "Setting up ChromeDriver..."
    pip install webdriver-manager selenium
    print_success "ChromeDriver setup complete"
    
    deactivate
}

setup_qwen3_service() {
    print_section "Setting Up Qwen3 TTS Service"
    
    cd "$SCRIPT_DIR"
    
    # Clone Qwen3 TTS API repository if not present
    local QWEN3_REPO="https://github.com/ETomberg391/EcneAI-Qwen-3-TTS-api.git"
    local QWEN3_DIR="EcneAI-Qwen-3-TTS-api"
    
    if [ ! -d "$QWEN3_DIR" ]; then
        print_info "Cloning Qwen3 TTS API repository..."
        git clone "$QWEN3_REPO" "$QWEN3_DIR"
        if [ $? -eq 0 ]; then
            print_success "Repository cloned successfully"
        else
            print_error "Failed to clone repository. Please check your internet connection."
            exit 1
        fi
    else
        print_info "Qwen3 TTS API directory already exists"
        
        # Check if existing venv is broken and needs recreation
        if [ -d "$QWEN3_DIR/venv" ]; then
            print_info "Checking existing Qwen3 virtual environment..."
            # Try to activate and check if pip works
            if ! "$QWEN3_DIR/venv/bin/pip" --version > /dev/null 2>&1; then
                print_warning "Qwen3 virtual environment is broken (pip not working)"
                print_info "Removing broken virtual environment..."
                rm -rf "$QWEN3_DIR/venv"
                print_success "Broken virtual environment removed"
            else
                print_success "Qwen3 virtual environment is working"
            fi
        fi
    fi
    
    if [ -f "setup_qwen3.sh" ]; then
        print_info "Running Qwen3 setup script..."
        chmod +x setup_qwen3.sh
        bash setup_qwen3.sh
        print_success "Qwen3 service setup complete"
    else
        print_error "setup_qwen3.sh not found!"
        print_info "Attempting manual Qwen3 setup..."
        
        # Manual setup fallback
        if [ -d "EcneAI-Qwen-3-TTS-api" ]; then
            cd EcneAI-Qwen-3-TTS-api
            
            if [ ! -d "venv" ]; then
                $PYTHON_CMD -m venv venv
            fi
            
            source venv/bin/activate
            
            if [ -f "requirements.txt" ]; then
                pip install -r requirements.txt
            fi
            
            deactivate
            cd "$SCRIPT_DIR"
            print_success "Manual Qwen3 setup complete"
        else
            print_error "EcneAI-Qwen-3-TTS-api directory not found!"
            exit 1
        fi
    fi
}

configure_environment() {
    print_section "Environment Configuration"
    
    cd "$SCRIPT_DIR"
    
    # Check if .env exists
    if [ ! -f "settings/.env" ]; then
        print_info "Creating .env file from template..."
        
        if [ -f "settings/env.example" ]; then
            cp settings/env.example settings/.env
            print_success ".env file created"
        else
            print_warning "env.example not found, creating minimal .env"
            cat > settings/.env << 'EOF'
# TTS Configuration
TTS_PROVIDER=qwen3
QWEN3_PORT=8000
QWEN3_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base

# API Keys (ADD YOUR OWN)
OPENAI_API_KEY=your_openai_api_key_here
BRAVE_API_KEY=your_brave_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Model Configuration
WHISPER_MODEL=base
DEFAULT_LLM_MODEL=gpt-4o-mini

# Paths
CONTENT_DIR=Content_Library
OUTPUT_DIR=Finished_Podcasts
EOF
            print_success "Minimal .env file created"
        fi
    else
        print_info ".env file already exists"
    fi
    
    # Ensure TTS_PROVIDER is set to qwen3
    if grep -q "TTS_PROVIDER" settings/.env; then
        # Update existing setting
        sed -i 's/TTS_PROVIDER=.*/TTS_PROVIDER=qwen3/' settings/.env
    else
        # Add setting
        echo "TTS_PROVIDER=qwen3" >> settings/.env
    fi
    print_success "TTS_PROVIDER set to qwen3 in .env"
    
    # Configure QWEN3 settings if not present
    if ! grep -q "QWEN3_PORT" settings/.env; then
        echo "" >> settings/.env
        echo "# Qwen3 TTS Configuration" >> settings/.env
        echo "QWEN3_PORT=8000" >> settings/.env
        echo "QWEN3_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base" >> settings/.env
        print_success "Qwen3 configuration added to .env"
    fi
    
    # Prompt for API keys
    print_section "API Key Configuration"
    print_info "The following API keys are needed for full functionality:"
    echo "  - OPENAI_API_KEY (Required for LLM processing)"
    echo "  - BRAVE_API_KEY (Required for web search)"
    echo "  - ELEVENLABS_API_KEY (Optional - alternative TTS)"
    echo ""
    
    read -p "Would you like to add/edit API keys now? (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # OpenAI API Key
        read -p "Enter OpenAI API Key (press Enter to keep existing): " openai_key
        if [ ! -z "$openai_key" ]; then
            sed -i "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$openai_key/" settings/.env
        fi
        
        # Brave API Key
        read -p "Enter Brave API Key (press Enter to keep existing): " brave_key
        if [ ! -z "$brave_key" ]; then
            sed -i "s/BRAVE_API_KEY=.*/BRAVE_API_KEY=$brave_key/" settings/.env
        fi
        
        print_success "API keys updated"
    fi
}

create_directories() {
    print_section "Creating Directory Structure"
    
    cd "$SCRIPT_DIR"
    
    mkdir -p Content_Library
    mkdir -p Finished_Podcasts
    mkdir -p logs
    mkdir -p settings/characters
    mkdir -p settings/voices
    
    print_success "Directories created"
}

create_launcher_scripts() {
    print_section "Creating Launcher Scripts"
    
    cd "$SCRIPT_DIR"
    
    # Main launcher script
    cat > launch_podcaster.sh << 'EOF'
#!/bin/bash

# Ecne AI Podcaster Launcher
# Starts both the Qwen3 TTS service and the main application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting Ecne AI Podcaster with Qwen3 TTS...${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    if [ -n "$QWEN3_PID" ]; then
        kill $QWEN3_PID 2>/dev/null
        echo "  - Qwen3 TTS service stopped"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start Qwen3 TTS Service
echo "1. Starting Qwen3 TTS Service..."
cd EcneAI-Qwen-3-TTS-api
source venv/bin/activate
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level info > ../logs/qwen3_service.log 2>&1 &
QWEN3_PID=$!
cd "$SCRIPT_DIR"

echo "   PID: $QWEN3_PID"
echo "   Log: logs/qwen3_service.log"
echo ""

# Wait for service to be ready
echo "2. Waiting for Qwen3 TTS to be ready..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}   Qwen3 TTS is ready!${NC}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# Check if service is actually running
if ! kill -0 $QWEN3_PID 2>/dev/null; then
    echo -e "${RED}Qwen3 TTS service failed to start!${NC}"
    echo "Check logs/qwen3_service.log for details."
    exit 1
fi

# Launch Control Panel
echo "3. Starting Control Panel..."
echo ""
source venv/bin/activate
python control_panel_app.py

# Cleanup when control panel exits
cleanup
EOF

    chmod +x launch_podcaster.sh
    print_success "Created launch_podcaster.sh"
    
    # Quick start script (Qwen3 only)
    cat > start_qwen3.sh << 'EOF'
#!/bin/bash
# Quick start for Qwen3 TTS service only

cd "$(dirname "$0")/EcneAI-Qwen-3-TTS-api" || exit 1
source venv/bin/activate
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level info
EOF

    chmod +x start_qwen3.sh
    print_success "Created start_qwen3.sh"
    
    # Test script
    cat > test_tts.sh << 'EOF'
#!/bin/bash
# Test Qwen3 TTS functionality

echo "Testing Qwen3 TTS..."

# Test health endpoint
if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "✓ Qwen3 TTS service is running"
else
    echo "✗ Qwen3 TTS service is not running"
    echo "  Start it with: ./start_qwen3.sh"
    exit 1
fi

# Test speakers endpoint
echo ""
echo "Available speakers:"
curl -s http://127.0.0.1:8000/v1/speakers | $PYTHON_CMD -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8000/v1/speakers

echo ""
echo "Test complete!"
EOF

    chmod +x test_tts.sh
    print_success "Created test_tts.sh"
}

# ============================================
# Main Installation Flow
# ============================================

main() {
    print_header
    
    # Run all setup steps
    check_system
    setup_host_venv
    setup_qwen3_service
    configure_environment
    create_directories
    create_launcher_scripts
    
    # Final summary
    print_section "Installation Complete!"
    
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           🎉 Setup Complete! You're ready to go! 🎉          ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Next Steps:${NC}"
    echo ""
    echo "1. ${YELLOW}Start everything${NC}:"
    echo "   ./launch_podcaster.sh"
    echo ""
    echo "2. ${YELLOW}Or start Qwen3 TTS manually:${NC}"
    echo "   ./start_qwen3.sh"
    echo "   Then in another terminal: python control_panel_app.py"
    echo ""
    echo "3. ${YELLOW}Test the TTS service:${NC}"
    echo "   ./test_tts.sh"
    echo ""
    echo "4. ${YELLOW}Access the web interface:${NC}"
    echo "   http://127.0.0.1:7860 (Control Panel)"
    echo "   http://127.0.0.1:8000/docs (Qwen3 API docs)"
    echo ""
    echo -e "${CYAN}Configuration:${NC}"
    echo "  - Settings file: settings/.env"
    echo "  - Voice configs: settings/voices/"
    echo "  - Logs: logs/"
    echo ""
    echo -e "${CYAN}Voice Options:${NC}"
    echo "  Qwen3 has 9 preset speakers: Chelsie, Ryan, Xavier, Ethan,"
    echo "  Anna, Aiden, Chloe, XavierAlt, and Daisy"
    echo ""
    echo -e "${MAGENTA}Happy Podcasting! 🎙️${NC}"
    echo ""
}

# Run main if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
