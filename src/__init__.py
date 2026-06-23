"""
Source package initialization.

The presence of this file tells the Python interpreter that the 'src' directory
should be treated as a recognizable Python module. 

This is what allows absolute imports to work flawlessly across the entire project,
ensuring statements like `from src.schemas import ClaimModel` and 
`from src.config import config` execute without throwing pathing errors.
"""