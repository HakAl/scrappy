"""Shared fixtures and helpers for protocol conformance tests.

This module provides utilities for verifying that classes correctly
implement protocol interfaces.
"""

import inspect
from typing import (
    Protocol,
    get_type_hints,
    get_origin,
    get_args,
    Any,
    Callable,
    List,
    Tuple,
    Optional,
    runtime_checkable,
)


def get_protocol_methods(protocol: type) -> List[str]:
    """Get list of method names defined by a protocol.

    Args:
        protocol: Protocol class to inspect

    Returns:
        List of method names (excluding dunder methods)
    """
    methods = []
    for name, member in inspect.getmembers(protocol):
        # Skip dunder methods and private methods
        if name.startswith('_'):
            continue
        # Skip class variables that aren't methods
        if not callable(member) and not isinstance(inspect.getattr_static(protocol, name), property):
            continue
        # Include methods and properties
        methods.append(name)
    return methods


def get_protocol_properties(protocol: type) -> List[str]:
    """Get list of property names defined by a protocol.

    Args:
        protocol: Protocol class to inspect

    Returns:
        List of property names
    """
    properties = []
    for name in dir(protocol):
        if name.startswith('_'):
            continue
        try:
            attr = inspect.getattr_static(protocol, name)
            if isinstance(attr, property):
                properties.append(name)
        except AttributeError:
            continue
    return properties


def assert_has_method(implementation: type, method_name: str) -> None:
    """Assert that implementation has the specified method.

    Args:
        implementation: Class to check
        method_name: Name of method to look for

    Raises:
        AssertionError: If method is missing
    """
    assert hasattr(implementation, method_name), (
        f"{implementation.__name__} missing method '{method_name}'"
    )


def assert_has_property(implementation: type, property_name: str) -> None:
    """Assert that implementation has the specified property.

    Args:
        implementation: Class to check
        property_name: Name of property to look for

    Raises:
        AssertionError: If property is missing
    """
    assert hasattr(implementation, property_name), (
        f"{implementation.__name__} missing property '{property_name}'"
    )


def assert_method_callable(implementation: type, method_name: str) -> None:
    """Assert that the method is callable on the implementation.

    Args:
        implementation: Class to check
        method_name: Name of method to check

    Raises:
        AssertionError: If method is not callable
    """
    attr = getattr(implementation, method_name, None)
    # Allow both regular methods and classmethods/staticmethods
    is_callable = (
        callable(attr) or
        isinstance(inspect.getattr_static(implementation, method_name), (classmethod, staticmethod))
    )
    assert is_callable, (
        f"{implementation.__name__}.{method_name} is not callable"
    )


def get_method_signature(cls: type, method_name: str) -> Optional[inspect.Signature]:
    """Get the signature of a method on a class.

    Args:
        cls: Class to inspect
        method_name: Name of method

    Returns:
        Signature object or None if method doesn't exist
    """
    method = getattr(cls, method_name, None)
    if method is None:
        return None
    try:
        return inspect.signature(method)
    except (ValueError, TypeError):
        return None


def assert_signature_compatible(
    implementation: type,
    protocol: type,
    method_name: str
) -> None:
    """Assert that implementation's method signature is compatible with protocol.

    Checks that:
    - Implementation has at least as many parameters as protocol requires
    - Required parameters match in position
    - Implementation may have additional optional parameters

    Args:
        implementation: Implementation class
        protocol: Protocol class
        method_name: Method to check

    Raises:
        AssertionError: If signatures are incompatible
    """
    proto_sig = get_method_signature(protocol, method_name)
    impl_sig = get_method_signature(implementation, method_name)

    if proto_sig is None:
        return  # Can't check if protocol method has no signature

    if impl_sig is None:
        raise AssertionError(
            f"{implementation.__name__}.{method_name} has no inspectable signature"
        )

    # Get parameters (excluding 'self')
    proto_params = list(proto_sig.parameters.values())
    impl_params = list(impl_sig.parameters.values())

    # Filter out 'self' parameter
    if proto_params and proto_params[0].name == 'self':
        proto_params = proto_params[1:]
    if impl_params and impl_params[0].name == 'self':
        impl_params = impl_params[1:]

    # Count required parameters in protocol (no default)
    proto_required = sum(
        1 for p in proto_params
        if p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    )

    # Count required parameters in implementation
    impl_required = sum(
        1 for p in impl_params
        if p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    )

    # Implementation should not require more params than protocol
    # (implementation can have more optional params)
    if impl_required > proto_required:
        raise AssertionError(
            f"{implementation.__name__}.{method_name} requires {impl_required} parameters "
            f"but protocol only requires {proto_required}"
        )


def assert_implements_protocol(
    implementation: type,
    protocol: type,
    check_signatures: bool = True
) -> None:
    """Verify a class implements all protocol methods with correct signatures.

    Args:
        implementation: Class to verify
        protocol: Protocol class that defines the interface
        check_signatures: If True, also verify method signatures

    Raises:
        AssertionError: If implementation doesn't conform to protocol
    """
    # Get protocol methods
    methods = get_protocol_methods(protocol)
    properties = get_protocol_properties(protocol)

    # Check all methods are present
    for method_name in methods:
        assert_has_method(implementation, method_name)
        # Skip signature check for properties
        if method_name not in properties:
            assert_method_callable(implementation, method_name)
            if check_signatures:
                assert_signature_compatible(implementation, protocol, method_name)

    # Check all properties are present
    for prop_name in properties:
        assert_has_property(implementation, prop_name)


def assert_isinstance_protocol(
    instance: Any,
    protocol: type
) -> None:
    """Assert that an instance passes isinstance() check against a runtime_checkable protocol.

    Args:
        instance: Object instance to check
        protocol: Protocol class (must be @runtime_checkable)

    Raises:
        AssertionError: If isinstance check fails
        TypeError: If protocol is not runtime_checkable
    """
    # Verify protocol is runtime_checkable
    if not getattr(protocol, '_is_runtime_checkable', True):
        raise TypeError(
            f"{protocol.__name__} is not @runtime_checkable, cannot use isinstance()"
        )

    assert isinstance(instance, protocol), (
        f"{type(instance).__name__} instance does not pass isinstance() "
        f"check for {protocol.__name__}"
    )
