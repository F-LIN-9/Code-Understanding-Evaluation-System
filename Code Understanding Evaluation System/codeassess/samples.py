# -*- coding: utf-8 -*-
"""示例代码库：15 个典型程序/核心代码片段，覆盖循环、数组、递归、字符串、
排序查找、类与对象等课程知识点，用于演示与生成测评案例集。
"""

SAMPLES = [
    {
        "title": "求列表元素之和与平均值",
        "course": "程序设计基础",
        "language": "python",
        "kp": "循环, 累加, 边界条件",
        "source": '''def average(scores):
    total = 0
    for s in scores:
        total = total + s
    if len(scores) == 0:
        return 0
    return total / len(scores)


if __name__ == "__main__":
    data = [88, 92, 79, 95]
    print(average(data))
''',
    },
    {
        "title": "查找列表中的最大值",
        "course": "程序设计基础",
        "language": "python",
        "kp": "循环, 比较, 列表下标",
        "source": '''def max_value(nums):
    if not nums:
        return None
    best = nums[0]
    for x in nums:
        if x > best:
            best = x
    return best


print(max_value([3, 9, 2, 7]))
''',
    },
    {
        "title": "冒泡排序实现",
        "course": "数据结构与算法",
        "language": "python",
        "kp": "嵌套循环, 交换, 时间复杂度",
        "source": '''def bubble_sort(arr):
    n = len(arr)
    for i in range(n - 1):
        for j in range(n - 1 - i):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
''',
    },
    {
        "title": "二分查找（有序数组）",
        "course": "数据结构与算法",
        "language": "python",
        "kp": "while循环, 折半, 边界条件",
        "source": '''def binary_search(data, target):
    low = 0
    high = len(data) - 1
    while low <= high:
        mid = (low + high) // 2
        if data[mid] == target:
            return mid
        elif data[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
''',
    },
    {
        "title": "递归求阶乘",
        "course": "程序设计基础",
        "language": "python",
        "kp": "递归, 终止条件, 函数调用",
        "source": '''def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)


print(factorial(5))
''',
    },
    {
        "title": "递归求斐波那契数列",
        "course": "数据结构与算法",
        "language": "python",
        "kp": "递归, 重复计算, 时间复杂度",
        "source": '''def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


print(fib(10))
''',
    },
    {
        "title": "字符串反转与回文判断",
        "course": "程序设计基础",
        "language": "python",
        "kp": "字符串, 切片, 条件判断",
        "source": '''def is_palindrome(text):
    cleaned = text.lower().replace(" ", "")
    reversed_text = cleaned[::-1]
    if cleaned == reversed_text:
        return True
    return False


print(is_palindrome("Never odd or even"))
''',
    },
    {
        "title": "列表去重并保持原顺序",
        "course": "数据结构与算法",
        "language": "python",
        "kp": "集合, 循环, 列表操作",
        "source": '''def unique(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


print(unique([1, 3, 1, 2, 3, 4]))
''',
    },
    {
        "title": "学生成绩统计与排序",
        "course": "面向对象程序设计",
        "language": "python",
        "kp": "字典, 排序, lambda",
        "source": '''def top_students(scores, k):
    pairs = list(scores.items())
    pairs.sort(key=lambda p: p[1], reverse=True)
    result = []
    for i in range(min(k, len(pairs))):
        result.append(pairs[i][0])
    return result


scores = {"张明": 88, "李婷": 95, "王浩": 76}
print(top_students(scores, 2))
''',
    },
    {
        "title": "判断素数",
        "course": "程序设计基础",
        "language": "python",
        "kp": "循环, 取余, 边界条件",
        "source": '''def is_prime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i = i + 1
    return True


print(is_prime(97))
''',
    },
    {
        "title": "括号匹配（栈的应用）",
        "course": "数据结构与算法",
        "language": "python",
        "kp": "栈, 字符串, 边界条件",
        "source": '''def is_balanced(expr):
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for ch in expr:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack:
                return False
            if stack[-1] != pairs[ch]:
                return False
            stack.pop()
    return len(stack) == 0


print(is_balanced("{[()]}"))
''',
    },
    {
        "title": "冒泡排序（Java 数组版）",
        "course": "面向对象程序设计",
        "language": "java",
        "kp": "数组, 嵌套循环, 交换",
        "source": '''public class BubbleSort {
    public static void sort(int[] arr) {
        int n = arr.length;
        for (int i = 0; i < n - 1; i++) {
            for (int j = 0; j < n - 1 - i; j++) {
                if (arr[j] > arr[j + 1]) {
                    int tmp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = tmp;
                }
            }
        }
    }

    public static void main(String[] args) {
        int[] data = {5, 2, 9, 1};
        sort(data);
        for (int v : data) {
            System.out.print(v + " ");
        }
    }
}
''',
    },
    {
        "title": "学生类与平均分计算（Java）",
        "course": "面向对象程序设计",
        "language": "java",
        "kp": "类与对象, 构造方法, 数组遍历",
        "source": '''public class StudentScore {
    private String name;
    private double[] scores;

    public StudentScore(String name, double[] scores) {
        this.name = name;
        this.scores = scores;
    }

    public double average() {
        double sum = 0;
        for (double s : scores) {
            sum += s;
        }
        if (scores.length == 0) {
            return 0;
        }
        return sum / scores.length;
    }

    public boolean isPassed() {
        return average() >= 60;
    }
}
''',
    },
    {
        "title": "二分查找（C++ 实现）",
        "course": "数据结构与算法",
        "language": "cpp",
        "kp": "数组, while循环, 折半",
        "source": '''#include <iostream>
using namespace std;

int binarySearch(int arr[], int n, int target) {
    int low = 0;
    int high = n - 1;
    while (low <= high) {
        int mid = (low + high) / 2;
        if (arr[mid] == target) {
            return mid;
        } else if (arr[mid] < target) {
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return -1;
}
''',
    },
    {
        "title": "矩阵转置（C++ 二维数组）",
        "course": "程序设计基础",
        "language": "cpp",
        "kp": "二维数组, 嵌套循环, 下标",
        "source": '''#include <iostream>
using namespace std;

void transpose(int a[3][3], int b[3][3]) {
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            b[j][i] = a[i][j];
        }
    }
}
''',
    },
]