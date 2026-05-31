function getStyles() {
  return `
    <style>
      body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 600px;
        margin: 0 auto;
        padding: 20px;
        background-color: #f5f5f5;
      }

      .container {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 30px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      }

      h1 {
        color: #1a1a1a;
        font-size: 28px;
        margin-bottom: 10px;
        border-bottom: 3px solid #ff6b35;
        padding-bottom: 10px;
      }

      h2 {
        color: #2c3e50;
        font-size: 22px;
        margin-top: 30px;
        margin-bottom: 15px;
      }

      .section {
        margin-bottom: 40px;
      }

      .item {
        margin-bottom: 25px;
        padding-bottom: 20px;
        border-bottom: 1px solid #eee;
      }

      .item:last-child {
        border-bottom: none;
      }

      .item-title {
        font-size: 18px;
        font-weight: 600;
        color: #1a1a1a;
        margin-bottom: 5px;
      }

      .item-tagline {
        color: #666;
        font-size: 14px;
        margin-bottom: 10px;
      }

      .item-meta {
        font-size: 13px;
        color: #999;
        margin-top: 8px;
      }

      .video-container {
        margin: 15px 0;
        max-width: 100%;
      }

      video, iframe {
        max-width: 100%;
        height: auto;
        border-radius: 4px;
      }

      a {
        color: #ff6b35;
        text-decoration: none;
      }

      a:hover {
        text-decoration: underline;
      }

      .footer {
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid #eee;
        font-size: 12px;
        color: #999;
        text-align: center;
      }

      @media only screen and (max-width: 600px) {
        body {
          padding: 10px;
        }

        .container {
          padding: 20px;
        }

        h1 {
          font-size: 24px;
        }

        h2 {
          font-size: 20px;
        }
      }
    </style>
  `;
}

module.exports = { getStyles };
