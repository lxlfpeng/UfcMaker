const http = require("http")
const fs = require("fs")
const path = require("path")

const blockedFiles = ["secret.txt", ".exe"]
const ignore = [
  ".git",
  ".vscode",
  ".DS_Store",
  "node_modules",
  "package-lock.json",
  ".htaccess",
]

const server = http.createServer((req, res) => {
  const filePath = path.join(__dirname, req.url)

  // Check if file is blocked
  if (blockedFiles.some((file) => filePath.includes(file))) {
    res.statusCode = 403
    res.end("Access to this file is forbidden")
    return
  }

  // Check if file exists
  fs.access(filePath, fs.constants.F_OK, (err) => {
    if (err) {
      res.statusCode = 404
      res.end("File not found")
      return
    }

    // Check if file is a directory
    fs.stat(filePath, (err, stats) => {
      if (err) {
        res.statusCode = 500
        res.end("Internal server error")
        return
      }

      if (stats.isDirectory()) {
        // Serve index file if it exists
        const indexFilePath = path.join(filePath, "index.html")
        fs.access(indexFilePath, fs.constants.F_OK, (err) => {
          if (err) {
            // Generate directory listing
            fs.readdir(filePath, (err, files) => {
              if (err) {
                res.statusCode = 500
                res.end("Internal server error")
                return
              }

              const html = `
                <html>
                  <head>
                    <title>Directory listing for ${req.url}</title>
                    <style>
                        li {
                            font-size: 50px;
                           }
                    </style>
                  </head>
                  <body>
                    <h1>Directory listing for ${req.url}</h1>
                    <ul>
                      ${files
                        .filter((item) => !ignore.includes(item))
                        .sort()
                        .map(
                          (file) =>
                            `<li><a href="${path.join(
                              req.url,
                              file
                            )}">${file}</a></li>`
                        )
                        .join("")}
                    </ul>
                  </body>
                </html>
              `

              res.setHeader("Content-Type", "text/html")
              res.end(html)
            })
          } else {
            // Serve index file
            serveFile(indexFilePath, res)
          }
        })
      } else {
        // Serve file
        serveFile(filePath, res)
      }
    })
  })
})

function serveFile(filePath, res) {
  const fileStream = fs.createReadStream(filePath)
  fileStream.on("open", () => {
    res.setHeader("Content-Type", getContentType(filePath))
    fileStream.pipe(res)
  })
  fileStream.on("error", (err) => {
    res.statusCode = 500
    res.end("Internal server error")
  })
}

function getContentType(filePath) {
  const extname = path.extname(filePath)
  switch (extname) {
    case ".html":
      return "text/html"
    case ".css":
      return "text/css"
    case ".js":
      return "text/javascript"
    case ".json":
      return "application/json"
    case ".png":
      return "image/png"
    case ".jpg":
    case ".jpeg":
      return "image/jpeg"
    default:
      return "application/octet-stream"
  }
}

server.listen(3300, () => {
  console.log("Server listening on port 3300")
})