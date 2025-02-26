from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
import os

# PostgreSQL Connection Parameters
# user = os.environ["DB_USER"]
# password = os.environ["DB_PASSWORD"]
# host = os.environ["DB_HOST"]
# port = os.environ["DB_PORT"]
# database = os.environ["DB_DB"]
user = "aman_user" # Default to 'root'
password ="securepassword"# Default empty (set password if configured)
host =  "localhost" # Default to localhost
port = "3306"  # MySQL default port
database =  "AMAN"  # Default database (change as needed)

connection_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

# Connection Pooling Settings
connect_args = {}  # PostgreSQL requires no special connect args
pool_size = 10  # Increase this if needed (default: 5)
max_overflow = 20  # How many extra connections can be created (default: 10)
pool_timeout = 30  # Seconds before timing out
pool_recycle = 1800  # Recycle connections every 30 minutes

# SQLAlchemy Engine with Connection Pooling
engine = create_engine(
    connection_str,
    connect_args=connect_args,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=pool_timeout,
    pool_recycle=pool_recycle,
)

db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    """
    Initialize the database by creating all defined tables.
    """
    # Import all models to ensure they are registered before table creation
    # Example: from yourapplication.models import SomeModel
    Base.metadata.create_all(bind=engine)
