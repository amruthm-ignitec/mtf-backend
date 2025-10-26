# DonorIQ Backend API

A production-ready FastAPI backend for the DonorIQ tissue donation management system.

## 🚀 Features

- **Role-based Authentication** (Admin, Doc Uploader, Medical Director)
- **Donor Management** with priority flags
- **Document Upload & Processing** with Azure Blob Storage
- **AI-powered Document Analysis** using OpenAI
- **RESTful API** with comprehensive endpoints
- **Production-ready** with logging, error handling, and monitoring

## 🏗️ Architecture

```
mtf-backend/
├── app/
│   ├── api/v1/           # API routes and endpoints
│   ├── core/             # Core configuration and utilities
│   ├── database/         # Database configuration
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   └── services/         # Business logic services
├── alembic/              # Database migrations
├── scripts/              # Utility scripts
├── tests/                # Test suite
├── logs/                 # Application logs
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Local development setup
└── run.py               # Production startup script
```

## 🛠️ Tech Stack

- **FastAPI** - Modern, fast web framework
- **PostgreSQL** - Reliable database
- **SQLAlchemy** - ORM for database operations
- **Alembic** - Database migrations
- **Azure Blob Storage** - File storage
- **OpenAI** - AI document analysis
- **JWT** - Authentication tokens
- **Docker** - Containerization

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 13+
- Docker (optional)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd mtf-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
cp env.example .env
# Edit .env with your configuration
```

### 3. Database Setup

```bash
# Run migrations
alembic upgrade head

# Create admin user
python scripts/create_admin_user.py
```

### 4. Start the Application

```bash
# Development
python run.py

# Production
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## 🐳 Docker Deployment

### Local Development

```bash
docker-compose up -d
```

### Production Build

```bash
docker build -t donoriq-backend .
docker run -p 8000:8000 --env-file .env donoriq-backend
```

## 📊 API Documentation

Once running, access the interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## 🔐 Authentication

The API uses JWT-based authentication. Default admin credentials:

- **Email**: `admin@donoriq.com`
- **Password**: `admin123`

⚠️ **Change the default password in production!**

## 🧪 Testing

```bash
# Run API tests
python tests/test_api.py

# Run with pytest
pytest tests/
```

## 📈 Monitoring

### Health Checks

- **Health**: `GET /health`
- **Metrics**: `GET /metrics`

### Logging

Logs are written to:
- **Console**: Development
- **File**: `logs/app.log` (Production)

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `SECRET_KEY` | JWT secret key | Required |
| `DEBUG` | Debug mode | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MAX_FILE_SIZE_MB` | Max file upload size | `500` |

### Security Settings

- Password minimum length: 8 characters
- JWT token expiration: 30 minutes
- Max login attempts: 5
- Lockout duration: 15 minutes

## 🚀 Production Deployment

### 1. Environment Setup

```bash
# Set production environment variables
export DEBUG=false
export LOG_LEVEL=INFO
export SECRET_KEY=your-secure-secret-key
```

### 2. Database Migration

```bash
alembic upgrade head
```

### 3. Create Admin User

```bash
python scripts/create_admin_user.py
```

### 4. Start Production Server

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 📝 API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `GET /api/v1/auth/me` - Get current user
- `POST /api/v1/auth/logout` - User logout

### Donors
- `GET /api/v1/donors/` - List all donors
- `POST /api/v1/donors/` - Create new donor
- `GET /api/v1/donors/{id}` - Get donor details
- `PUT /api/v1/donors/{id}` - Update donor
- `PUT /api/v1/donors/{id}/priority` - Update donor priority
- `DELETE /api/v1/donors/{id}` - Delete donor (Admin only)

### Documents
- `GET /api/v1/documents/` - List all documents
- `POST /api/v1/documents/upload` - Upload document
- `GET /api/v1/documents/{id}` - Get document details
- `PUT /api/v1/documents/{id}` - Update document
- `DELETE /api/v1/documents/{id}` - Delete document
- `GET /api/v1/documents/donor/{donor_id}` - Get donor documents

### Users (Admin only)
- `GET /api/v1/users/` - List all users
- `POST /api/v1/users/` - Create new user
- `GET /api/v1/users/{id}` - Get user details
- `PUT /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user

## 🔒 Security Best Practices

1. **Change default passwords** immediately
2. **Use strong SECRET_KEY** for JWT tokens
3. **Enable HTTPS** in production
4. **Restrict CORS origins** to your domains
5. **Regular security updates** of dependencies
6. **Monitor logs** for suspicious activity

## 🐛 Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check `DATABASE_URL` format
   - Ensure PostgreSQL is running
   - Verify credentials

2. **Authentication Issues**
   - Verify `SECRET_KEY` is set
   - Check JWT token expiration
   - Ensure user exists in database

3. **File Upload Errors**
   - Check file size limits
   - Verify Azure Blob Storage credentials
   - Ensure file types are allowed

### Logs

Check application logs for detailed error information:

```bash
tail -f logs/app.log
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 📞 Support

For support and questions:
- Create an issue in the repository
- Contact the development team
- Check the documentation

---

**DonorIQ Backend API** - Production-ready tissue donation management system.