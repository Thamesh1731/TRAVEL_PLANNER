# 🌍 AI Travel Guide

A smart travel planning application with AI recommendations, real-time weather forecasts, and interactive maps.

## ✨ Features

- 🗓️ **Smart Planning** - Date-based travel planning with automatic day calculation
- 🌤️ **Weather Forecasts** - Real-time weather data and temperature ranges
- 🤖 **AI Recommendations** - Personalized travel guides powered by Groq AI
- 🗺️ **Interactive Maps** - Place markers with clickable Google reviews
- 🔐 **User Authentication** - Secure login with Google OAuth support

## 🚀 How to Run

### Prerequisites

- Node.js (v18+)
- Python (v3.8+)
- MongoDB Atlas account (free)

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd Travel
   ```

2. **Install dependencies**
   ```bash
   npm install
   pip install -r requirements.txt
   ```

3. **Setup environment variables**
   
   Create a `.env` file in the root directory (see `.env.example` for template):
   ```env
   MONGODB_URI=your_mongodb_connection_string
   JWT_SECRET=your_secret_key
   GOOGLE_CLIENT_ID=your_google_client_id
   OPENWEATHER_API_KEY=your_openweather_key
   GROQ_API_KEY=your_groq_key
   PY_PLANNER_URL=http://localhost:8001
   PORT=3000
   ```

### Running the App

**Option 1: Using PowerShell Script (Windows)**
```powershell
.\start-app.ps1
```

**Option 2: Manual Start (All Platforms)**

Open two terminal windows:

**Terminal 1 - Python Backend:**
```bash
cd python
uvicorn app:app --reload --port 8001
```

**Terminal 2 - Node.js Frontend:**
```bash
node server.js
```

Then open your browser to: **http://localhost:3000**

## 🔑 API Keys Setup

### Required APIs (All Free Tier):

1. **OpenWeather API** - [Get key here](https://openweathermap.org/api)
2. **Groq API** - [Get key here](https://console.groq.com)
3. **MongoDB Atlas** - [Setup here](https://www.mongodb.com/atlas)
4. **Google OAuth** (Optional) - [Setup here](https://console.cloud.google.com)

## 📁 Project Structure

```
Travel/
├── public/          # Frontend files
├── python/          # FastAPI backend
├── server.js        # Node.js server
├── .env             # Environment variables (not in repo)
├── .env.example     # Environment template
└── README.md        # This file
```

## 🛠️ Tech Stack

- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Node.js, Express.js
- **Python API**: FastAPI, Uvicorn
- **Database**: MongoDB
- **APIs**: OpenWeather, Groq AI, OpenStreetMap

## 📝 License

MIT License - feel free to use this project!

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

---

**Made with ❤️ for travelers**
