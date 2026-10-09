TiTaN AI Robot — Main Dashboard / API

Deploy this folder as its own Vercel project. Do not include render.yaml.

Included: Flask dashboard, existing TiTaN API endpoints, templates, requirements, Vercel routing.

Environment variables: set GEMINI_API_KEY (and GEMINI_MODEL if your app uses it) in Vercel Project Settings > Environment Variables. Never commit API keys.

Mobile Vision Node: deploy the separate TiTaN_Mobile_Vision_Node folder as a second Vercel project. After deployment, open the Vision Node with the main backend URL as a query parameter, for example:
https://YOUR-VISION-NODE.vercel.app/?api=https://YOUR-MAIN-DASHBOARD.vercel.app

IMPORTANT CAMERA LIMITATION: the current backend keeps the latest camera frame in Python process memory and streams it from /video_stream. Vercel serverless instances do not guarantee shared process memory or persistent MJPEG connections. These ZIPs preserve the existing architecture and configure cross-origin uploads, but reliable dashboard video on Vercel still requires a shared transport/storage or WebRTC relay. Do not assume the live dashboard feed is fixed just by deploying both projects.
