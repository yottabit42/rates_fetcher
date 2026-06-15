FROM python:3.12-bookworm

WORKDIR /app

# Prevent python from buffering stdout/stderr so logs appear immediately
ENV PYTHONUNBUFFERED=1

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Install pip dependencies
RUN pip install --no-cache-dir curl_cffi lxml beautifulsoup4 requests

# Setup cron job to run at noon every day
# We inject the current PATH so cron can find python3 and pip
# We pipe to tee and redirect to /proc/1/fd/1 so cron logs show up in docker console
RUN echo "PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" > /etc/cron.d/scraper-cron && \
    echo "0 12 * * * root cd /app && bash ./run_scraper.sh 2>&1 | tee -a /app/scraper.log > /proc/1/fd/1" >> /etc/cron.d/scraper-cron
RUN chmod 0644 /etc/cron.d/scraper-cron

# On container start, run the scraper once in the background, then start cron in the foreground
CMD bash -c "cd /app && bash ./run_scraper.sh 2>&1 | tee -a /app/scraper.log > /proc/1/fd/1 & exec cron -f"
