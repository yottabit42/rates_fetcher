FROM python:3.12-bookworm

WORKDIR /app

# Prevent python from buffering stdout/stderr so logs appear immediately
ENV PYTHONUNBUFFERED=1

# Install cron, tzdata, chromium, and chromium-driver for Selenium fallback
RUN apt-get update && apt-get install -y cron tzdata chromium chromium-driver && rm -rf /var/lib/apt/lists/*

# Install python dependencies including rebrowser-playwright, curl_cffi, lxml, and selenium
RUN pip install --no-cache-dir rebrowser-playwright curl_cffi lxml beautifulsoup4 requests selenium webdriver-manager

# Install playwright browsers and their OS-level dependencies
RUN python3 -m rebrowser_playwright install --with-deps chromium

# Setup cron job to run at noon every day
# Inject the current PATH so cron can find python3 and pip
# Pipe to tee and redirect to /proc/1/fd/1 so cron logs show up in docker console
RUN echo "PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" > /etc/cron.d/scraper-cron && \
    echo "0 12 * * * root cd /app && bash ./run_scraper.sh 2>&1 | tee /app/scraper.log > /proc/1/fd/1" >> /etc/cron.d/scraper-cron
RUN chmod 0644 /etc/cron.d/scraper-cron

# On container start, run the scraper once in the background, then start cron in the foreground
CMD bash -c "cd /app && bash ./run_scraper.sh 2>&1 | tee /app/scraper.log > /proc/1/fd/1 & exec cron -f"
