# Criteria evaluator module
# Import using importlib to avoid circular import issues
import importlib.util
import os

# Get the path to the parent criteria_evaluator.py file
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
criteria_evaluator_file = os.path.join(parent_dir, 'criteria_evaluator.py')

# Load the module from the file
spec = importlib.util.spec_from_file_location("app.services.criteria_evaluator_module", criteria_evaluator_file)
criteria_evaluator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(criteria_evaluator_module)

# Export the criteria_evaluator instance
criteria_evaluator = criteria_evaluator_module.criteria_evaluator

__all__ = ['criteria_evaluator']
