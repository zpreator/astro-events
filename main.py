import ephem


def main():
    mars = ephem.Mars()  # type: ignore
    mars.compute("2025/10/13")
    print(f"Mars current position: RA={mars.ra}, Dec={mars.dec}")


if __name__ == "__main__":
    main()
