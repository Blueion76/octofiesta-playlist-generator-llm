"""Batch processing utilities for efficient downloads"""

import asyncio
import logging
from typing import List, Dict, Callable, Any, Optional


logger = logging.getLogger(__name__)


class BatchProcessor:
    """Batch processor for async operations with concurrency control"""
    
    def __init__(self, batch_size: int = 5, concurrency: int = 3):
        """Initialize batch processor.
        
        Args:
            batch_size: Number of items per batch
            concurrency: Maximum concurrent operations
        """
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.processed = 0
        self.failed = 0
        
    async def process_batch(
        self,
        items: List[Any],
        process_func: Callable,
        *args,
        **kwargs
    ) -> List[tuple[bool, Any]]:
        """Process items in batches with concurrency control.
        
        Args:
            items: List of items to process
            process_func: Function to process each item
            *args: Additional positional arguments for process_func
            **kwargs: Additional keyword arguments for process_func
            
        Returns:
            List of (success, result) tuples
        """
        results = []
        
        # Process in batches
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            logger.info(f"Processing batch {i//self.batch_size + 1}/{(len(items)-1)//self.batch_size + 1} ({len(batch)} items)")
            
            # Process batch items with concurrency limit
            semaphore = asyncio.Semaphore(self.concurrency)
            
            async def process_with_semaphore(item):
                async with semaphore:
                    try:
                        result = await process_func(item, *args, **kwargs)
                        self.processed += 1
                        return True, result
                    except Exception as e:
                        self.failed += 1
                        logger.error(f"Failed to process item: {e}")
                        return False, str(e)
            
            # Process batch concurrently
            batch_results = await asyncio.gather(
                *[process_with_semaphore(item) for item in batch],
                return_exceptions=True
            )
            
            results.extend(batch_results)
            
            # Brief pause between batches
            if i + self.batch_size < len(items):
                await asyncio.sleep(1)
        
        logger.info(f"Batch processing complete: {self.processed} succeeded, {self.failed} failed")
        return results


def process_in_batches(
    items: List[Any],
    process_func: Callable,
    batch_size: int = 5,
    concurrency: int = 3
) -> List[tuple[bool, Any]]:
    """Convenience function to process items in batches synchronously.
    
    Args:
        items: List of items to process
        process_func: Function to process each item
        batch_size: Number of items per batch
        concurrency: Maximum concurrent operations
        
    Returns:
        List of (success, result) tuples
    """
    processor = BatchProcessor(batch_size, concurrency)
    return asyncio.run(processor.process_batch(items, process_func))
