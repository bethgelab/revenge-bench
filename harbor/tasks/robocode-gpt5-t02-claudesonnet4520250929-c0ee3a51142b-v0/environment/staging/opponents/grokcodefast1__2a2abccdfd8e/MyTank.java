package custom;
import robocode.Robot;
import robocode.ScannedRobotEvent;

public class MyTank extends Robot {
    public void run() {
        setAdjustRadarForRobotTurn(true); // Adjust radar when robot turns
        setAdjustGunForRobotTurn(true); // Adjust gun when robot turns
        while(true) {
            // Wall avoidance
            if (getX() < 50 || getX() > getBattleFieldWidth() - 50 ||
                getY() < 50 || getY() > getBattleFieldHeight() - 50) {
                turnRight(90);
            }
            turnRadarRight(360); // Continuous scanning
            ahead(100);
            turnRight(Math.random() * 60 - 30); // Random turn to evade
            back(100);
            turnRight(Math.random() * 60 - 30);
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Distance-based firepower: stronger for closer enemies
        double power = Math.min(3.0, 400.0 / e.getDistance());
        turnGunRight(e.getBearing());
        fire(power);
    }
}