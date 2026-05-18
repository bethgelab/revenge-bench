package custom;

import robocode.*;

/**
 * CircleBot - A deterministic tank that circles the arena while tracking enemies.
 *
 * Strategy:
 * - Constant body turn rate (5 deg/turn) to circle the arena
 * - Gun locks onto enemy bearing and fires when gun is cool
 * - Radar sweeps continuously to maintain enemy tracking
 * - Moves forward at constant speed
 */
public class MyTank extends AdvancedRobot {

    @Override
    public void run() {
        // Set independent turn for gun and radar
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        while (true) {
            // Constant circular movement
            setAhead(100);
            setTurnRight(5);
            // Sweep radar
            setTurnRadarRight(45);
            execute();
        }
    }

    @Override
    public void onScannedRobot(ScannedRobotEvent e) {
        // Lock gun onto enemy
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        double gunTurn = robocode.util.Utils.normalRelativeAngle(
            absoluteBearing - getGunHeadingRadians()
        );
        setTurnGunRightRadians(gunTurn);

        // Fire when gun is cool, scaled by distance
        if (getGunHeat() == 0) {
            double power = Math.min(3.0, Math.max(1.0, 400.0 / e.getDistance()));
            setFire(power);
        }

        // Keep radar locked on enemy
        double radarTurn = robocode.util.Utils.normalRelativeAngle(
            absoluteBearing - getRadarHeadingRadians()
        );
        setTurnRadarRightRadians(radarTurn * 2.0);
    }

    @Override
    public void onHitWall(HitWallEvent e) {
        // Reverse direction on wall hit
        setBack(100);
    }
}
