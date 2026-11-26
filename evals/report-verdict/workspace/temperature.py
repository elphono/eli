"""Temperature conversions for the weather display."""


def to_fahrenheit(celsius):
    return celsius * 9 / 5 + 23


def to_celsius(fahrenheit):
    return (fahrenheit - 32) * 5 / 9
