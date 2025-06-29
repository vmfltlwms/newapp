# git

# 실무에서는 브랜치 → 원격 등록 → 푸시

git init  
git add .
git commit -m "Initial commit"

# 새 브랜치 생성

# 현재 브랜치의 이름을 new로 바꾼다 브랜치 이름을 바꾸고 싶을 때

git branch -M main

# feature/login이라는 새 브랜치를 만들고 이동한다 새로운 브랜치를 만들 때

git checkout -b feature/login

# 원격 저장소 등록

git remote add origin https://github.com/username/repo.git

# 새 브런치에 저장

git push -u origin feature/login

# 최초 push

git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/username/repo.git
git push -u origin main

# 이후에는

git add .
git commit -m "Fix login bug"
git push # 원래 있던 main 브랜치에 푸시됨

# 1. ubuntu 실행

wsl -d Ubuntu

# 2. 가상환경 실행

source kim_env/bin/activate

kim_env\Scripts\activate

# redis server 실행행

sudo systemctl restart redis-server or

# 레디스 실행

sudo service redis-server restart
pwd : 1111
sudo service redis-server status

# 가상환경 만들기

python3 -m venv kim_env

pip 사용용
python -m pip install fastapi

#uv 사용 <= pip
uv python

python3 main.py

# ubuntu 설치치

wsl --install
sudo apt update
sudo apt install redis-server -y

# next.js + 타입스크립트 리액트 프로젝트

npx create-next-app@latest my-app --typescript

# ===== VPS/클라우드 서버 배포 가이드 =====

# 1. 서버 초기 설정 (Ubuntu 20.04/22.04)

sudo apt update && sudo apt upgrade -y

# 2. Node.js 설치 (최신 LTS 버전)

curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# 확인

node --version
npm --version

# 3. PM2 설치 (프로세스 관리자)

sudo npm install -g pm2

# 4. Nginx 설치 (리버스 프록시)

sudo apt install nginx -y
sudo systemctl start nginx
sudo systemctl enable nginx

# 5. 프로젝트 클론 및 설정

cd /var/www/
sudo git clone https://github.com/your-username/kiwoom-trading-app.git
sudo chown -R $USER:$USER kiwoom-trading-app
cd kiwoom-trading-app

# 6. 의존성 설치 및 빌드

npm install
npm run build

# 7. 환경변수 설정

sudo nano .env.production

# 내용:

# DATABASE_URL="your_production_database_url"

# KIWOOM_APP_KEY="your_app_key"

# KIWOOM_SECRET_KEY="your_secret_key"

# NEXTAUTH_URL="https://yourdomain.com"

# NEXTAUTH_SECRET="your_production_secret"

# 8. 데이터베이스 마이그레이션

npx prisma db push
npx prisma generate

# 9. PM2로 앱 실행

pm2 start npm --name "kiwoom-app" -- run start
pm2 save
pm2 startup

# 10. Nginx 설정

sudo nano /etc/nginx/sites-available/kiwoom-app

# Nginx 설정 파일 내용:

server {
listen 80;
server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

}

# 11. Nginx 설정 활성화

sudo ln -s /etc/nginx/sites-available/kiwoom-app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 12. SSL 인증서 설치 (Let's Encrypt)

sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# 13. 방화벽 설정

sudo ufw allow 22 # SSH
sudo ufw allow 80 # HTTP
sudo ufw allow 443 # HTTPS
sudo ufw enable

# ===== Docker 배포 =====

# Dockerfile

FROM node:18-alpine AS builder
WORKDIR /app
COPY package\*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

FROM node:18-alpine AS runner
WORKDIR /app
ENV NODE_ENV production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT 3000

CMD ["node", "server.js"]

# docker-compose.yml

version: '3.8'
services:
app:
build: .
ports: - "3000:3000"
environment: - DATABASE_URL=${DATABASE_URL}
      - KIWOOM_APP_KEY=${KIWOOM_APP_KEY} - KIWOOM_SECRET_KEY=${KIWOOM_SECRET_KEY}
depends_on: - postgres

postgres:
image: postgres:15
environment:
POSTGRES_DB: kiwoom_trading
POSTGRES_USER: postgres
POSTGRES_PASSWORD: password
volumes: - postgres_data:/var/lib/postgresql/data
ports: - "5432:5432"

nginx:
image: nginx:alpine
ports: - "80:80" - "443:443"
volumes: - ./nginx.conf:/etc/nginx/nginx.conf - ./ssl:/etc/nginx/ssl
depends_on: - app

volumes:
postgres_data:

# Docker 실행 명령어

docker-compose up -d

# ===== AWS/클라우드 배포 스크립트 =====

# AWS EC2 배포 스크립트

#!/bin/bash

# EC2 인스턴스 설정

echo "AWS EC2에 Next.js 앱 배포 시작..."

# 필수 패키지 설치

sudo yum update -y
sudo yum install -y git

# Node.js 설치

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install --lts
nvm use --lts

# 프로젝트 설정

cd /home/ec2-user
git clone https://github.com/your-username/kiwoom-trading-app.git
cd kiwoom-trading-app

# 환경변수 설정

echo "DATABASE_URL=your_database_url" > .env.production
echo "KIWOOM_APP_KEY=your_app_key" >> .env.production
echo "KIWOOM_SECRET_KEY=your_secret_key" >> .env.production

# 앱 빌드 및 실행

npm install
npm run build
npm install -g pm2
pm2 start npm --name "kiwoom-trading" -- run start
pm2 startup
pm2 save

echo "배포 완료! 포트 3000에서 실행 중"

# ===== 자동 배포 스크립트 =====

# deploy.sh

#!/bin/bash

APP_NAME="kiwoom-trading-app"
REPO_URL="https://github.com/your-username/kiwoom-trading-app.git"
APP_DIR="/var/www/$APP_NAME"

echo "🚀 자동 배포 시작..."

# 기존 앱 중지

pm2 stop $APP_NAME || true

# 최신 코드 풀

cd $APP_DIR
git pull origin main

# 의존성 업데이트 및 빌드

npm install
npm run build

# 데이터베이스 마이그레이션

npx prisma db push

# 앱 재시작

pm2 start npm --name $APP_NAME -- run start
pm2 save

echo "✅ 배포 완료!"

# 실행 권한 부여

chmod +x deploy.sh

# ===== 모니터링 설정 =====

# PM2 모니터링

pm2 monit

# 로그 확인

pm2 logs kiwoom-app

# 리소스 사용량 확인

pm2 status

# 자동 재시작 설정

pm2 start ecosystem.config.js

# ecosystem.config.js

module.exports = {
apps: [{
name: 'kiwoom-trading-app',
script: 'npm',
args: 'run start',
instances: 'max',
exec_mode: 'cluster',
env: {
NODE_ENV: 'production',
PORT: 3000
},
error_file: './logs/err.log',
out_file: './logs/out.log',
log_file: './logs/combined.log',
time: true
}]
}
