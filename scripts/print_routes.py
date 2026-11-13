from app.api.main import app
for r in sorted(app.routes, key=lambda x: x.path):
    print(r.path)