def calculate_average(numbers):
    total = 0
    for num in numbers:
        total = total + num
    return total / len(numbers)

def main():
    data = [1, 2, 3, 4, 5]
    result = calculate_average(data)
    print(f"Average: {result}")

if __name__ == "__main__":
    main()