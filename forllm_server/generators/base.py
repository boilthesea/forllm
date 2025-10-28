from abc import ABC, abstractmethod

class BaseGenerator(ABC):
    """
    Abstract base class for all content generators.
    """
    @abstractmethod
    def generate(self, request_details: dict, *args, **kwargs) -> dict:
        """
        The main method for a generator. It takes a dictionary of request details
        and performs the generation task.

        Args:
            request_details: A dictionary containing all necessary information
                             for the generation, such as prompt, model, parameters, etc.

        Returns:
            A dictionary containing the result of the generation, e.g.,
            {'status': 'complete', 'result_object_id': 123} or
            {'status': 'error', 'error_message': '...'}
        """
        pass